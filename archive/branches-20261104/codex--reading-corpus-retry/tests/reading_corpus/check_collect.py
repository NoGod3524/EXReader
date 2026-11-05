#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Offline collector protocol; invoked only by Actions before real collection."""
from contextlib import contextmanager
from email.utils import formatdate
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/reading_corpus'))
import collect

URL = 'https://publisher.invalid/original.pdf'
NOW = 1800000000


def response(data=b'original', url=URL):
    result = io.BytesIO(data)
    result.url = url
    return result


def error(code=429, retry_after=None, url=URL):
    headers = {} if retry_after is None else {'Retry-After': retry_after}
    return urllib.error.HTTPError(url, code, 'test response', headers, io.BytesIO())


@contextmanager
def network(results):
    elapsed = [0]

    def sleep(seconds):
        elapsed[0] += seconds

    with patch.object(collect.urllib.request, 'urlopen', side_effect=results) as opened, \
            patch.object(collect.time, 'monotonic', side_effect=lambda: elapsed[0]), \
            patch.object(collect.time, 'time', side_effect=lambda: NOW + elapsed[0]), \
            patch.object(collect.time, 'sleep', side_effect=sleep) as slept:
        yield opened, slept


class CollectorProtocol(unittest.TestCase):
    def test_429_then_success_honors_retry_after_seconds(self):
        with network([error(retry_after='3'), response()]) as (opened, slept):
            self.assertEqual(collect.fetch(URL, 8), (b'original', URL))
            self.assertEqual(opened.call_count, 2)
            slept.assert_called_once_with(3)

    def test_retry_after_http_date(self):
        date = formatdate(NOW + 7, usegmt=True)
        with network([error(retry_after=date), response()]) as (opened, slept):
            self.assertEqual(collect.fetch(URL, 8)[0], b'original')
            slept.assert_called_once_with(7)

    def test_429_exhaustion_fails_after_four_requests(self):
        with network([error() for _ in range(4)]) as (opened, slept):
            with self.assertRaises(urllib.error.HTTPError) as raised:
                collect.fetch(URL, 8)
            self.assertEqual(raised.exception.code, 429)
            self.assertEqual(opened.call_count, 4)
            self.assertEqual([call.args[0] for call in slept.call_args_list], [2, 4, 8])

    def test_retry_after_exceeding_total_window_fails_without_shortening(self):
        for value in ('180', '9' * 5000, formatdate(NOW + 181, usegmt=True)):
            with self.subTest(value=value[:50]), network([error(retry_after=value)]) as (opened, slept):
                with self.assertRaises(urllib.error.HTTPError):
                    collect.fetch(URL, 8)
                self.assertEqual(opened.call_count, 1)
                slept.assert_not_called()
        with network([error(retry_after='100'), error(retry_after='100')]) as (opened, slept):
            with self.assertRaises(urllib.error.HTTPError):
                collect.fetch(URL, 8)
            self.assertEqual(opened.call_count, 2)
            slept.assert_called_once_with(100)

    def test_remaining_retry_window_bounds_the_next_request_timeout(self):
        with network([error(retry_after='150'), response()]) as (opened, slept):
            self.assertEqual(collect.fetch(URL, 8)[0], b'original')
            self.assertEqual([call.kwargs['timeout'] for call in opened.call_args_list], [60, 30])

    def test_invalid_retry_after_uses_bounded_fallback(self):
        with network([error(retry_after='invalid'), response()]) as (opened, slept):
            self.assertEqual(collect.fetch(URL, 8)[0], b'original')
            slept.assert_called_once_with(2)

    def test_other_errors_fail_immediately(self):
        for failure in (error(404), error(503), urllib.error.URLError('connection failed')):
            with self.subTest(error=type(failure).__name__), network([failure]) as (opened, slept):
                with self.assertRaises(type(failure)):
                    collect.fetch(URL, 8)
                self.assertEqual(opened.call_count, 1)
                slept.assert_not_called()

    def test_byte_bound_is_preserved(self):
        with network([response(b'original!')]) as (opened, slept):
            with self.assertRaisesRegex(ValueError, 'download bound'):
                collect.fetch(URL, 8)
            self.assertEqual(opened.call_count, 1)
            slept.assert_not_called()

    def test_https_requirement_is_preserved(self):
        with network([]) as (opened, slept):
            with self.assertRaisesRegex(ValueError, 'HTTPS required'):
                collect.fetch('http://publisher.invalid/book', 8)
            opened.assert_not_called()
        for result in (response(url='http://publisher.invalid/book'), error(url='http://publisher.invalid/book')):
            with self.subTest(result=type(result).__name__), network([result]) as (opened, slept):
                with self.assertRaisesRegex(ValueError, 'HTTPS redirect required'):
                    collect.fetch(URL, 8)
                self.assertEqual(opened.call_count, 1)
                slept.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
