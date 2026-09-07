import gzip
import tempfile
import unittest
from pathlib import Path
from cidr import build, check


class CIDRTests(unittest.TestCase):
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
