"""Regression checks for event uniqueness, information boundaries and ambiguous matches."""
import unittest
import pandas as pd
from scripts.wp03_compare import split
from scripts.agent_comparison import match
from scripts.ingest import windows,START,END


class DesignTests(unittest.TestCase):
    def test_contiguous_windows(self):
        spans=list(windows())
        self.assertEqual((spans[0][0],spans[-1][1]),(START,END))
        self.assertTrue(all(x[1]==y[0] for x,y in zip(spans,spans[1:])))

    def test_purge_boundary_equality(self):
        t=pd.Timestamp("2026-08-01")
        h=pd.Timedelta(hours=1)
        frame=pd.DataFrame(dict(start=[t-5*h,t-4*h,t-3*h,t,t],decision=[t-3*h,t-2*h,t-h,t+h,t+h],
                                 evidence_start=[t-6*h,t-6*h,t-6*h,t-h,t-h],y=[0,1,1,0,1]))
        train,test=split(frame,t)
        self.assertEqual(list(train.index),[0,1])
        self.assertEqual(list(test.index),[3,4])

    def test_ambiguous_matches(self):
        t=pd.Timestamp("2026-07-01")
        events=pd.DataFrame(dict(sensor=["A","B"],start=[t,t],end=[t,t]))
        inv=[dict(_id="x",timestamp=t,station_id="s",decision="alert")]
        sites=[dict(_id="s",sensorIds=["A","B"])]
        self.assertEqual(match(events,inv,sites,"same_clock_confirmed").status.iloc[0],"ambiguous")
        twice=match(events.iloc[:1],inv+inv,sites,"same_clock_confirmed")
        self.assertTrue(twice.status.eq("multiple_investigations").all())
        with self.assertRaises(ValueError):match(events,inv,sites,"unknown")


if __name__=="__main__":
    unittest.main()
