# Copyright 2026- majvan (majvan@gmail.com)
'''
Tests for timequeue module.
'''

from collections import deque

import pytest

from dssim.timequeue import TQBinTree, TQBisect, NowQueue


@pytest.fixture(params=[TQBinTree, TQBisect], ids=['bintree', 'bisect'])
def queue_cls(request):
    return request.param


@pytest.fixture
def tq(queue_cls):
    return queue_cls()


def _pop_one(tq):
    '''Pop one event using only public TimeQueue API.'''
    t = tq.get_first_time()
    bucket = tq.pop_first_bucket()
    element = bucket.popleft()
    if bucket:
        tq.insertleft(t, bucket)
    return t, element


class TestTimeQueue:
    '''Test the time queue API behaviour on both implementations.'''

    def test1_init_empty(self, tq):
        assert not tq
        assert tq.event_count() == 0
        assert len(tq._queue) == 0

    def test2_add_element_builds_sorted_buckets(self, tq):
        tq.add_element(10, 'a')
        tq.add_element(0, 'b')
        tq.add_element(5, 'c')
        tq.add_element(5, 'd')
        assert tq
        assert tq.event_count() == 4
        assert [t for t, _ in tq._queue] == [0, 5, 10]
        assert [len(q) for _, q in tq._queue] == [1, 2, 1]
        assert list(tq._queue[1][1]) == ['c', 'd']

    def test3_pop_one_respects_global_and_bucket_fifo(self, tq):
        tq.add_element(10, 'a')
        tq.add_element(0, 'b')
        tq.add_element(5, 'c')
        tq.add_element(5, 'd')
        assert _pop_one(tq) == (0, 'b')
        assert _pop_one(tq) == (5, 'c')
        assert _pop_one(tq) == (5, 'd')
        assert _pop_one(tq) == (10, 'a')
        assert not tq
        assert tq.event_count() == 0

    def test4_get_first_time_and_pop_first_bucket(self, tq):
        tq.add_element(2, 'a')
        tq.add_element(2, 'b')
        tq.add_element(3, 'c')
        assert tq.get_first_time() == 2
        bucket = tq.pop_first_bucket()
        assert list(bucket) == ['a', 'b']
        assert tq.event_count() == 1
        assert tq.get_first_time() == 3

    def test5_insertleft_merges_with_same_time_bucket(self, tq):
        tq.add_element(1, 'a')
        tq.insertleft(1, deque(['b', 'c']))
        assert [t for t, _ in tq._queue] == [1]
        assert list(tq._queue[0][1]) == ['a', 'b', 'c']
        assert tq.event_count() == 3

    def test6_insertleft_prepends_earlier_bucket(self, tq):
        tq.add_element(5, 'x')
        tq.insertleft(1, deque(['a', 'b']))
        assert [t for t, _ in tq._queue] == [1, 5]
        assert _pop_one(tq) == (1, 'a')
        assert _pop_one(tq) == (1, 'b')
        assert _pop_one(tq) == (5, 'x')

    def test7_insertleft_later_time_keeps_sorted_order(self, tq):
        tq.add_element(1, 'a')
        tq.add_element(5, 'e')
        tq.insertleft(3, deque(['c', 'd']))
        assert [t for t, _ in tq._queue] == [1, 3, 5]
        assert _pop_one(tq) == (1, 'a')
        assert _pop_one(tq) == (3, 'c')
        assert _pop_one(tq) == (3, 'd')
        assert _pop_one(tq) == (5, 'e')

    def test8_infinite_time_is_valid(self, tq):
        tq.add_element(float('inf'), 'later')
        tq.add_element(10, 'now')
        assert _pop_one(tq) == (10, 'now')
        assert _pop_one(tq) == (float('inf'), 'later')

    def test9_delete_sub_filters_all_matching_subscribers(self, tq):
        sub_a, sub_b, sub_c = object(), object(), object()
        tq.add_element(2, (sub_a, {'a': 1, 'b': 2, 'c': 3}))
        tq.add_element(1, (sub_b, {'b': 1, 'c': 2, 'd': 3}))
        tq.add_element(3, (sub_c, {'x': 1, 'y': 2, 'z': 3}))
        tq.add_element(4, (sub_a, {'a': 10}))
        tq.delete_sub(sub_a)
        assert tq.event_count() == 2
        assert _pop_one(tq) == (1, (sub_b, {'b': 1, 'c': 2, 'd': 3}))
        assert _pop_one(tq) == (3, (sub_c, {'x': 1, 'y': 2, 'z': 3}))
        tq.delete_sub(sub_b)
        assert tq.event_count() == 0

    def test10_delete_val_filters_matching_values(self, tq):
        tq.add_element(2, {'a': 1, 'b': 2, 'c': 3})
        tq.add_element(1, {'b': 1, 'c': 2, 'd': 3})
        tq.add_element(3, {'x': 1, 'y': 2, 'z': 3})
        tq.add_element(4, {'a': 1, 'b': 2, 'c': 3, 'x': -1, 'y': -2})
        tq.delete_val({'x': 1, 'y': 2, 'z': 3})
        assert tq.event_count() == 3
        assert _pop_one(tq) == (1, {'b': 1, 'c': 2, 'd': 3})
        assert _pop_one(tq) == (2, {'a': 1, 'b': 2, 'c': 3})
        assert tq.event_count() == 1
        tq.delete_val({'a': 100, 'b': 2, 'c': 3, 'x': -1, 'y': -2})
        assert tq.event_count() == 1
        tq.delete_val({'a': 1, 'b': 2, 'c': 3, 'x': -1, 'y': -2})
        assert tq.event_count() == 0


class TestNowQueue:
    '''Test the NowQueue class behavior.'''

    @pytest.fixture
    def q(self):
        return NowQueue()

    def test1_init(self, q):
        assert len(q) == 0
        assert not q

    def test2_append_popleft(self, q):
        q.append('a')
        assert len(q) == 1
        assert q
        item = q.popleft()
        assert item == 'a'
        assert len(q) == 0
        assert not q

    def test3_fifo_order(self, q):
        q.append('first')
        q.append('second')
        q.append('third')
        assert len(q) == 3
        assert q.popleft() == 'first'
        assert q.popleft() == 'second'
        assert q.popleft() == 'third'
        assert len(q) == 0

    def test4_tuple_elements(self, q):
        consumer_a, consumer_b = object(), object()
        q.append((consumer_a, 'event1'))
        q.append((consumer_b, 'event2'))
        c, e = q.popleft()
        assert c is consumer_a
        assert e == 'event1'
        c, e = q.popleft()
        assert c is consumer_b
        assert e == 'event2'

    def test5_filter_constructor(self, q):
        consumer_a, consumer_b = object(), object()
        q.append((consumer_a, 'ev1'))
        q.append((consumer_b, 'ev2'))
        q.append((consumer_a, 'ev3'))
        filtered = NowQueue(item for item in q if item[0] is not consumer_a)
        assert len(filtered) == 1
        c, e = filtered.popleft()
        assert c is consumer_b
        assert e == 'ev2'
