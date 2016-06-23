# Description

This module uses image parsing to submit a captcha response to amazon using scrapy middleware.

It is accurate roughly 60% of the time.

The middleware checks for "Robot Check" in the title of the page and if the string is found, then it attempts to decode the captcha and submit the response.

# Usage 

In settings.py
```python
DOWNLOADER_MIDDLEWARES = {
    'captchabuster.RobotMiddleware': 450
}
```

# Installation

Clone the repository locally.

`pip install -e /path/to/captchabuster/`
