import os
import tempfile
import uuid
import logging
from cStringIO import StringIO

from BeautifulSoup import BeautifulSoup
from PIL import Image
import requests
from scrapy import FormRequest, Request
from scrapy.exceptions import IgnoreRequest
from scrapy.http.response.html import HtmlResponse

ROOT = os.path.abspath(os.path.dirname(__file__))
ICON_LOC = os.path.join(ROOT, 'iconset')


class CaptchaBuster(object):

    def __init__(self, captcha_loc):
        self.original = Image.open(captcha_loc).convert('P')
        self.temp_file = tempfile.TemporaryFile(suffix='.gif', prefix='CaptchaTemp_', dir=ROOT)
        self.image_segment_files = [tempfile.TemporaryFile(suffix='.gif', prefix='%d_ImageSegment_' % n, dir=ROOT) for n in range(6)]
        self.image_segments = []
        self.processed_captcha = Image.new('P', self.original.size, 255)

    @property
    def guess(self):
        self._pre_process_captcha()
        self._crop_partitions()
        return ''.join([p[0][1] for p in self._guess_characters()])

    @classmethod
    def from_url(cls, url, session=None):
        """
        Create a CaptchaBuster object from the url of a captcha.
        :param url: URL location of the captcha image
        :param session: requests.Session object. Use if you have an
            already generated session that you want to use instead of
            a default session.
        :type url: str
        :type session: requests.Session
        :return:
        :rtype: CaptchaBuster
        """
        if not session:
            session = requests.Session()
        url_tmp_pic = os.path.join(ROOT, 'captcha.jpg')
        with open(url_tmp_pic, 'wb') as f:
            f.write(session.get(url).content)

        return CaptchaBuster(url_tmp_pic)

    def _pre_process_captcha(self):
        """
        Scan the original image from top to bottom moving left to right and
            check if the pixel at location is below color value 10. If the pixel
            at location is within the threshold, write the pixel to the temp file.
        """
        for y in range(self.original.size[1]):
            for x in range(self.original.size[0]):
                pixel = self.original.getpixel((x, y))
                if pixel < 10:
                    self.processed_captcha.putpixel((x, y), 0)
        self.processed_captcha.save(self.temp_file, 'gif')

    def _crop_partitions(self):
        """
        Find discrete partitions within the preprocessed captcha
        to find regions containing individual characters. Returns an accumulated
        list of (start, end) coordinates for this region. Partitions are
        calculated based on the existence of characters within the image, as
        determined by surrounding white space.
        :return:
        """
        letters = []
        in_letter = False
        found_letter = False
        start, end = 0, 0

        for y in range(self.processed_captcha.size[0]):
            for x in range(self.processed_captcha.size[1]):
                pixel = self.processed_captcha.getpixel((y, x))
                if not pixel:
                    in_letter = True

            if not found_letter and in_letter:
                found_letter = True
                start = y

            if found_letter and not in_letter:
                found_letter = False
                end = y
                letters.append((start, end))

            in_letter = False

        count = 0
        for start, end in letters:
            crop_box = (start, 0, end, self.processed_captcha.size[1])
            part = self.processed_captcha.crop(crop_box)

            # If the segment of the image is too small to be a letter, ignore
            # the segment
            if part.size[0] < 15:
                pass
            else:
                part.save(self.image_segment_files[count], 'gif')
                self.image_segments.append(part)
                count += 1

    def _guess_characters(self):
        captcha = []
        for segment in self.image_segments:
            guess = []
            for letter in 'abcdefghijklmnopqrstuvwxyz':
                letter_dir = os.path.join(ICON_LOC, letter)
                for img in os.listdir(letter_dir):
                    if img != 'Thumbs.db' and img != '.gitignore':
                        tmp = Image.open(os.path.join(letter_dir, img))
                        s = segment.resize(tmp.size)
                        guess.append((self.relation(self.build_vector(tmp),
                                                    self.build_vector(s)), letter))
            guess.sort(reverse=True)
            captcha.append(guess)
        return captcha

    @classmethod
    def build_vector(cls, img):
        d1 = {}
        for count, i in enumerate(img.getdata()):
            d1[count] = i
        return d1

    @classmethod
    def relation(cls, concordance1, concordance2):
        """

        """
        relevance = 0
        for word, count in concordance1.iteritems():
            if word in concordance2 and count == concordance2[word]:
                if not count:
                    relevance += 5 if not count else 1
        return float(relevance)/float(len(concordance2))


def test():
    for t in range(5):
        session = requests.Session()
        response = session.get('http://www.amazon.com/errors/validateCaptcha')
        soup = BeautifulSoup(response.content)
        with open('./%d_captcha.jpg' % t, 'wb') as f:
            f.write(session.get(soup.find('img').get('src')).content)

        cb = CaptchaBuster('./%d_captcha.jpg' % t)
        print 'Pass %d:' % t, cb.guess


class RobotMiddleware(object):

    PRIORITY_ADJUST = 100
    MAX_RETRY = 3

    def __init__(self, crawler):
        self.crawler = crawler
        self.logger = logging.getLogger(self.__class__.__name__)

    def process_request(self, request, spider):
        return

    def process_exception(self, request, exception, spider):
        return

    def process_response(self, request, response, spider):
        self.logger.debug(request.meta)
        crack_count = request.meta.get('crack_retry_count', 0) + 1
        if crack_count >= self.MAX_RETRY:
            raise IgnoreRequest('Max retries exceeded for url (%s)' % request.meta.get('original_request', request).url)
        if isinstance(response, HtmlResponse) and 'robot check' in ''.join([x.strip().lower() for x in response.xpath('//title/text()').extract()]):
            self.crawler.stats.inc_value('robot_check')
            # Log the url of the original request that got blocked
            self.logger.warning('robot check (%s)' % request.url)

            soup = BeautifulSoup(response.body)
            form = soup.find('form')

            # url to send the captcha verification request
            form_url = 'http://www.amazon.com' + form.get('action')

            # get all input params in the form. the only ones that are in the form are hidden
            input_params = {x.get('name'): x.get('value') for x in form.findAll('input')}

            self.logger.debug('input_params: %s' % ' - '.join(['{}={}'.format(k, v) for k, v in input_params.items()]))

            # Sometimes the captcha cracker is wrong, which will redirect to another captcha and
            # we want to use the original request url for our referer.
            meta = {'target_url': form_url,
                    'params': input_params,
                    'referer_url': request.meta.get('referer_url') or response.url,
                    'original_request': request,
                    'is_captcha': True,
                    'crack_retry_count': crack_count}
            request.meta.update(meta)

            image_url = form.find('img').get('src')
            self.logger.debug('image_url=%s' % image_url)
            return Request(image_url, meta=request.meta, priority=self.PRIORITY_ADJUST, dont_filter=True, callback=request.callback)
        elif request.meta.get('is_captcha', False):
            self.logger.info('cracking (%s)' % request.url)
            params = request.meta.get('params')
            target_url = request.meta.get('target_url')
            # url_tmp_pic = os.path.join(ROOT, '%s_tmp_captcha.jpg' % uuid.uuid4())
            # with open(url_tmp_pic, 'wb') as f:
            #     f.write(response.body)
            try:  # Occasionally the image will come back with no data, so retry if that happens
                pic_data = StringIO(response.body)
                cb = CaptchaBuster(pic_data)
                params['field-keywords'] = cb.guess
                # os.remove(url_tmp_pic)
            except IOError:
                # os.remove(url_tmp_pic)
                return request.meta.get('original_request')
            self.logger.info('captcha_value=%s' % params['field-keywords'])
            request.meta['is_captcha'] = False
            meta = {'crack_retry_count': crack_count}
            request.meta.update(meta)
            return FormRequest(target_url, formdata=params, meta=request.meta, priority=self.PRIORITY_ADJUST, method='GET',
                               headers={'Referer': request.meta.get('referer_url'), 'Host': 'www.amazon.com'}, dont_filter=True, callback=request.callback)
        return response

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)


if __name__ == '__main__':
    logging.basicConfig(level=10)
    test()
