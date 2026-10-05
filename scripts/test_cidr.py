import gzip
import io
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from pathlib import Path
from cidr import build, check, main


class CIDRTests(unittest.TestCase):
    def test_month_transition_download_and_failure_preserves_published_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'source.gz'
            source.write_bytes(gzip.compress(
                b'1.0.0.0,1.0.0.7,CN\n2001:db8::,2001:db8::3,CN\n'))
            output = Path(tmp) / 'cn-cidr.list'
            baseline = build(source, '2026-09')
            output.write_text(baseline)
            argv = ['cidr.py', 'update', '--release', '2026-10', '--output', str(output)]
            url = 'https://download.db-ip.com/free/dbip-country-lite-2026-10.csv.gz'

            def respond(request, timeout):
                self.assertEqual(request.full_url, url)
                self.assertEqual(request.get_header('User-agent'),
                                 'joe-rules/1.0 (+https://github.com/wangpao/joe-rules)')
                self.assertEqual(timeout, 120)
                return io.BytesIO(source.read_bytes())

            with patch('sys.argv', argv), patch('cidr.urllib.request.urlopen', side_effect=respond) as fetch:
                main()
                fetch.assert_called_once()
                self.assertEqual(output.read_text(), build(source, '2026-10'))
                main()
                fetch.assert_called_once()  # Already current: do not download again.

            output.write_text(baseline)
            error = HTTPError(url, 403, 'Forbidden', {}, None)
            with patch('sys.argv', argv), patch('cidr.urllib.request.urlopen', side_effect=error):
                with self.assertRaises(HTTPError): main()
            self.assertEqual(output.read_text(), baseline)

    def test_exact_country_filter_and_range_conversion(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'data.gz'
            with gzip.open(source, 'wt') as f:
                f.write('1.0.0.0,1.0.0.0,US\n1.0.0.1,1.0.0.3,CN\n1.0.0.4,1.0.0.7,CN\n2001:db8::,2001:db8::3,CN\n')
            text = build(source, '2026-09')
            self.assertEqual(check(text), {4: 7, 6: 4})
            self.assertIn('IP-CIDR,1.0.0.1/32', text)
            self.assertNotIn('IP-CIDR,1.0.0.0/', text)
            with gzip.open(source, 'wt') as f:
                f.write('1.0.0.0,1.0.0.7,CN\n1.0.0.4,1.0.0.8,CN\n')
            with self.assertRaises(ValueError): build(source, '2026-09')

    def test_reject_bad_output(self):
        for text in ['IP-CIDR,0.0.0.0/0', 'IP-CIDR6,1.0.0.0/24',
                     'IP-CIDR,1.0.0.1/24',
                     'IP-CIDR,1.0.0.0/24\nIP-CIDR,1.0.0.0/25\nIP-CIDR6,2001:db8::/64']:
            with self.assertRaises(ValueError): check(text)


if __name__ == '__main__': unittest.main()
