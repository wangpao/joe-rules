import copy
from pathlib import Path
import unittest
import rules as r

class RoutingTests(unittest.TestCase):
    def test_real_lists_and_priority(self):
        docs={f:r.parse((r.ROOT/f).read_text()) for f in r.FILES}
        r.check(docs)
        def route(host):
            host=host.lower().rstrip('.')
            for file in ('global-direct.list','explicit-proxy.list','cn-services.list'):
                if any(host==d if k=='full' else r.within(host,d) for k,d in r.all_rules(docs[file])): return file
            return None
        for host in ('mesu.apple.com','officecdn.microsoft.com','dl.steam.clngaa.com'):
            self.assertEqual(route(host),'global-direct.list')
        for host in ('chatgpt.com','raw.githubusercontent.com','www.youtube.com','steamcommunity.com','WWW.GOOGLE.COM.'):
            self.assertEqual(route(host),'explicit-proxy.list')
        self.assertEqual(route('api.bilibili.com'),'cn-services.list')
        for host in ('wetv.qq.com','evilbilibili.com','google.com.evil.net','customer.akamaized.net','random.livekit.cloud','icloud.com','store.steampowered.com'):
            self.assertIsNone(route(host))
        for doc in docs.values():
            self.assertEqual(r.parse(r.render(doc)),doc)

    def test_conflict_semantics(self):
        self.assertTrue(r.overlap(('domain','qq.com'),('full','wetv.qq.com')))
        self.assertFalse(r.overlap(('full','qq.com'),('full','wetv.qq.com')))
        self.assertFalse(r.overlap(('domain','qq.com'),('domain','notqq.com')))
        a=r.ListFile([], 'a'*40,[r.Group('a',rules=[('domain','qq.com')])])
        c=r.ListFile([], 'a'*40,[r.Group('b',rules=[('full','wetv.qq.com')])])
        with self.assertRaises(ValueError): r.check({'a':a,'b':c})

    def test_upstream_filters_affiliation_and_cycles(self):
        source=r.Source({'a':'include:b @cn @-!cn','b':'include:c','c':'one.cn @cn &alias\ntwo.com @cn @!cn\nthree.com'})
        self.assertEqual({x[1] for x in source.resolve('a')},{'one.cn'})
        self.assertEqual({x[1] for x in source.resolve('alias')},{'one.cn'})
        with self.assertRaises(ValueError): r.Source({'a':'include:b','b':'include:a'}).resolve('a')
        with self.assertRaises(ValueError): source.resolve('missing')

    def test_delta_does_not_import_old_excluded_domains(self):
        old=r.Source({'x':'example.com\nold-unselected.net'})
        new=r.Source({'x':'example.com\nold-unselected.net\nnew-service.net\nforeign.net @!cn\nads.net @ads\ncloudfront.net'})
        doc=r.ListFile([], 'a'*40,[r.Group('x',rules=[('domain','example.com')],sources=['x'],mode='delta')])
        changes,skipped=r.update(doc,old,new,'b'*40,'DIRECT')
        self.assertEqual(set(r.all_rules(doc)),{('domain','example.com'),('domain','new-service.net')})
        self.assertEqual(doc.revision,'b'*40)
        # Repeated updates are stable even if the saved baseline is older than the fetched source.
        again=copy.deepcopy(doc)
        changes,_=r.update(again,old,new,'b'*40,'DIRECT')
        self.assertEqual(changes,[])

    def test_maintain_removal_and_attribute_change(self):
        old=r.Source({'x':'example.com\nremoved.com'})
        new=r.Source({'x':'example.com\nfull:overseas.example.com @!cn\nnew.net'})
        doc=r.ListFile([], 'a'*40,[r.Group('x',rules=[('full','www.example.com'),('domain','removed.com')],sources=['x'])])
        changes,_=r.update(doc,old,new,'b'*40,'DIRECT')
        self.assertEqual(r.all_rules(doc),[('full','www.example.com')])
        self.assertEqual(len(changes),1)
        doc.groups[0].rules=[('domain','example.com')]
        r.update(doc,old,new,'b'*40,'DIRECT')
        self.assertEqual(r.all_rules(doc),[])

if __name__=='__main__': unittest.main()
