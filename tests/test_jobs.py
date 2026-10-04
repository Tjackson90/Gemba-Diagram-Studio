import threading
import time
import unittest
from services.jobs import JobRunner, check_cancelled
from services.documents import ExportJob


class JobTests(unittest.TestCase):
    def test_completion_on_polling_thread_and_busy_guard(self):
        runner=JobRunner();gate=threading.Event();results=[]
        main=threading.get_ident()
        try:
            runner.submit(lambda: gate.wait(2),lambda result: results.append(threading.get_ident()),results.append)
            with self.assertRaises(RuntimeError):runner.submit(lambda:None,results.append,results.append)
            gate.set()
            for _ in range(100):
                runner.poll()
                if results:break
                time.sleep(.01)
            self.assertEqual(results,[main])
            self.assertFalse(runner.busy)
        finally:runner.close()

    def test_cancellation(self):
        runner=JobRunner();gate=threading.Event();results=[]
        def work():
            gate.wait(2);check_cancelled()
        try:
            runner.submit(work,lambda _:results.append('unexpected success'),results.append)
            runner.cancel();gate.set()
            for _ in range(100):
                runner.poll()
                if results:break
                time.sleep(.01)
            self.assertEqual(results,['Operation cancelled'])
        finally:runner.close()
