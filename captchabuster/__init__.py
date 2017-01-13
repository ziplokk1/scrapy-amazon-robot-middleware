import urllib
import os
import logging
from cStringIO import StringIO

from PIL import Image
import requests
from collections import defaultdict

# This way when using the lib for only requests, then it wont raise an error when loading the module.
try:
    from scrapy.exceptions import IgnoreRequest
    from scrapy.http.response.html import HtmlResponse
except ImportError:
    pass

# BeautifulSoup isnt necessary to use the captchabuster class.
try:
    from BeautifulSoup import BeautifulSoup
except ImportError:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        pass

ROOT = os.path.abspath(os.path.dirname(__file__))
ICON_LOC = os.path.join(ROOT, 'iconset')


class CaptchaBuster(object):

    def __init__(self, captcha_loc):
        self.original = Image.open(captcha_loc).convert('P')
        self.temp_file = StringIO()
        self.image_segment_files = [StringIO() for n in range(6)]
        self.image_segments = []
        self.processed_captcha = Image.new('P', self.original.size, 255)

    @property
    def guess(self):
        self._pre_process_captcha()
        self._crop_partitions()
        return ''.join(self._guess_characters())

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
        io = StringIO(session.get(url, headers={'Accept': 'image/png;q=0.8,*/*;q=0.9'}).content)
        return CaptchaBuster(io)

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
            for letter, img_data_list in images.items():
                guess.extend(map(
                    lambda x: (self.relation(x['data'], segment.resize(x['image'].size).getdata()), letter),
                    img_data_list))
            guess = max(guess)
            captcha.append(guess[1])
        return captcha

    @classmethod
    def relation(cls, concordance1, concordance2):
        """

        """
        r = 0
        l = len(concordance1)
        for i in xrange(l):
            if (not concordance1[i]) and (concordance1[i] == concordance2[i]):
                r += 5
        return r/float(l)


def crack_from_requests(session, content):
    soup = BeautifulSoup(content)
    form = soup.find('form')

    action = 'http://www.amazon.com' + form.get('action')
    params = {x.get('name'): x.get('value') for x in form.findAll('input')}

    url = form.find('img').get('src')
    cb = CaptchaBuster.from_url(url, session)
    params['field-keywords'] = cb.guess

    url = action + '?' + urllib.urlencode(params)
    return session.get(url)


def load_images():
    logging.getLogger('captchabuster').info('preprocessing images...')
    d = defaultdict(list)
    for letter in 'abcdefghijklmnopqrstuvwxyz':
        letter_dir = os.path.join(ICON_LOC, letter)
        for img in os.listdir(letter_dir):
            if img != 'Thumbs.db' and img != '.gitignore':
                i = Image.open(os.path.join(letter_dir, img))
                v = i.getdata()
                d[letter].append({'image': i, 'data': v})
    return d


images = load_images()


def test():
    # for t in range(5):
    session = requests.Session()
    response = session.get('http://www.amazon.com/errors/validateCaptcha')
    soup = BeautifulSoup(response.content)
    # with open('./%d_captcha.jpg' % t, 'wb') as f:
    #     f.write(session.get(soup.find('img').get('src')).content)

    # cb = CaptchaBuster('./%d_captcha.jpg' % t)
    cb = CaptchaBuster(StringIO(session.get(soup.find('img').get('src')).content))
    print cb.guess
    # print 'Pass %d:' % t, cb.guess


class SessionTransferMiddleware(object):
    """
    Attach a new cookie jar to request when the status code is in the handle list.
    """

    current_cookie = 1
    handle = [503]

    def __init__(self, crawler):
        self.logger = logging.getLogger(self.__class__.__name__)

    def process_response(self, request, response, spider):
        if response.status in self.handle:
            cookie = self.current_cookie + 1
            self.logger.info('transferring request to new cookiejar. cookiejar={} {}'.format(cookie, request))
            meta = request.meta
            meta = meta.update({'cookiejar': cookie})
            self.current_cookie = cookie
            return request.replace(meta=meta)
        return response

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)


class RobotMiddleware(object):

    PRIORITY_ADJUST = 100
    MAX_RETRY = 20

    def __init__(self, crawler):
        self.crawler = crawler
        self.logger = logging.getLogger(self.__class__.__name__)
        self.cracking = False

    def request_image(self, request, response):

        # Im using beautiful soup because recursive element selection is built in and makes it easier
        # to parse the form inputs out into a dict.
        soup = BeautifulSoup(response.body)
        form = soup.find('form')

        action = 'http://www.amazon.com' + form.get('action')
        params = {x.get('name'): x.get('value') for x in form.findAll('input')}
        url = form.find('img').get('src')

        meta = {
            'form_action': action,
            'form_params': params,
            'original_request': request.meta.get('original_request') or request,
            'crack_retry_count': request.meta.get('crack_retry_count', 0) + 1,
            'image_request': True,
            'from_captchabuster_middleware': True
        }

        request.meta.update(meta)
        return request.replace(url=url, dont_filter=True)

    def process_image(self, request, response):
        form_params = request.meta.get('form_params')
        form_action = request.meta.get('form_action')

        # Occasionally the image will come back with no data or no image but instead html,
        # so retry the original request if that happens so that it filters back down the middleware
        try:
            picture = StringIO(response.body)
            cb = CaptchaBuster(picture)
            form_params['field-keywords'] = cb.guess
        except IOError:
            self.logger.warning('error processing image. {}'.format(response))
            return request.meta.get('original_request').replace(dont_filter=True)
        request.meta['image_request'] = False
        request.meta['captcha_submit'] = True
        url = form_action + '?' + urllib.urlencode(form_params)
        return request.replace(url=url, dont_filter=True)

    def process_response(self, request, response, spider):

        if request.meta.get('crack_retry_count', 0) > self.MAX_RETRY:
            raise IgnoreRequest('Max retries exceeded %s' % request.meta.get('original_request', request))

        if isinstance(response, HtmlResponse) and 'robot check' in ''.join([x.strip().lower() for x in response.xpath('//title/text()').extract()]):
            self.cracking = True
            self.crawler.stats.inc_value('robot_check')
            # Log the url of the original request that got blocked
            self.logger.warning('robot check {}'.format(request.meta.get('original_request') or request))
            return self.request_image(request, response)
        elif request.meta.get('image_request', False):
            self.logger.debug('processing image {}'.format(request))
            return self.process_image(request, response)
        else:
            self.cracking = False
            return response

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)


if __name__ == '__main__':
    logging.basicConfig(level=10)
    test()
