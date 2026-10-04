import math,time
from app.surebet import allocation
from app.models import Quote

def test_basic_arb():
    qs=[Quote('A',2.10,'Betclic',time.time(),'x'),Quote('B',2.10,'Fortuna',time.time(),'x')]
    r=allocation(qs,50,{'Betclic':1.0,'Fortuna':1.0})
    assert r and r[2]>2.0

def test_tax_kills_small_edge():
    qs=[Quote('A',2.10,'Superbet',time.time(),'x'),Quote('B',2.10,'STS',time.time(),'x')]
    r=allocation(qs,50,{'Superbet':0.88,'STS':0.88})
    assert r is None
