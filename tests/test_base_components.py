import unittest

from dssim.base_components import (
    DSQueue,
    DSLifoQueue,
    DSKeyQueue,
    DSResource,
    DSPriorityResource,
    DSPriorityPreemption,
)


class _Owner:
    pass


class TestDSQueue(unittest.TestCase):

    def setUp(self):
        self.q = DSQueue()

    def test1_init_empty(self):
        self.assertEqual(len(self.q), 0)
        self.assertFalse(self.q)
        self.assertIsNone(self.q.head)
        self.assertIsNone(self.q.tail)

    def test2_append_popleft_fifo(self):
        self.q.append('a')
        self.q.append('b')
        self.q.append('c')
        self.assertEqual(len(self.q), 3)
        self.assertTrue(self.q)
        self.assertEqual(self.q.popleft(), 'a')
        self.assertEqual(self.q.popleft(), 'b')
        self.assertEqual(self.q.popleft(), 'c')
        self.assertEqual(len(self.q), 0)

    def test3_appendleft(self):
        self.q.append('b')
        self.q.append('c')
        self.q.appendleft('a')
        self.assertEqual(self.q.popleft(), 'a')
        self.assertEqual(self.q.popleft(), 'b')

    def test4_pop_from_tail(self):
        self.q.append('x')
        self.q.append('y')
        self.assertEqual(self.q.pop(), 'y')
        self.assertEqual(self.q.pop(), 'x')

    def test5_head_tail(self):
        self.q.append(1)
        self.q.append(2)
        self.q.append(3)
        self.assertEqual(self.q.head, 1)
        self.assertEqual(self.q.tail, 3)

    def test6_contains(self):
        self.q.append('alpha')
        self.q.append('beta')
        self.assertIn('alpha', self.q)
        self.assertNotIn('gamma', self.q)

    def test7_iter(self):
        items = [10, 20, 30]
        for i in items:
            self.q.append(i)
        self.assertEqual(list(self.q), items)

    def test8_getitem(self):
        self.q.append('x')
        self.q.append('y')
        self.assertEqual(self.q[0], 'x')
        self.assertEqual(self.q[1], 'y')

    def test9_setitem(self):
        self.q.append('old')
        self.q[0] = 'new'
        self.assertEqual(self.q[0], 'new')

    def test10_pop_at_head(self):
        self.q.append('a')
        self.q.append('b')
        self.q.append('c')
        self.assertEqual(self.q.pop_at(0), 'a')
        self.assertEqual(list(self.q), ['b', 'c'])

    def test11_pop_at_middle(self):
        self.q.append('a')
        self.q.append('b')
        self.q.append('c')
        self.assertEqual(self.q.pop_at(1), 'b')
        self.assertEqual(list(self.q), ['a', 'c'])

    def test12_pop_at_tail(self):
        self.q.append('a')
        self.q.append('b')
        self.q.append('c')
        self.assertEqual(self.q.pop_at(2), 'c')
        self.assertEqual(list(self.q), ['a', 'b'])

    def test13_remove_item(self):
        self.q.append('a')
        self.q.append('b')
        self.q.remove('a')
        self.assertEqual(list(self.q), ['b'])

    def test14_remove_missing_raises(self):
        self.q.append('a')
        with self.assertRaises(ValueError):
            self.q.remove('z')

    def test15_remove_if_matches(self):
        for i in range(5):
            self.q.append(i)
        changed = self.q.remove_if(lambda e: e % 2 == 0)
        self.assertTrue(changed)
        self.assertEqual(list(self.q), [1, 3])

    def test16_remove_if_no_match(self):
        self.q.append(1)
        self.q.append(3)
        changed = self.q.remove_if(lambda e: e % 2 == 0)
        self.assertFalse(changed)
        self.assertEqual(list(self.q), [1, 3])

    def test17_remove_if_duplicates(self):
        self.q.append('x')
        self.q.append('x')
        self.q.append('y')
        changed = self.q.remove_if(lambda e: e == 'x')
        self.assertTrue(changed)
        self.assertEqual(list(self.q), ['y'])

    def test18_clear(self):
        self.q.append(1)
        self.q.append(2)
        self.q.clear()
        self.assertEqual(len(self.q), 0)
        self.assertIsNone(self.q.head)

    def test19_append_returns_item(self):
        obj = object()
        retval = self.q.append(obj)
        self.assertIs(retval, obj)

    def test20_enqueue_dequeue_fifo_default(self):
        self.q.enqueue('a')
        self.q.enqueue('b')
        self.q.enqueue('c')
        self.assertEqual(self.q.peek(), 'a')
        self.assertEqual(self.q.dequeue(), 'a')
        self.assertEqual(self.q.dequeue(), 'b')
        self.assertEqual(self.q.dequeue(), 'c')

    def test21_peek_empty(self):
        self.assertIsNone(self.q.peek())


class TestDSLifoQueue(unittest.TestCase):

    def setUp(self):
        self.q = DSLifoQueue()

    def test1_lifo_order(self):
        self.q.enqueue('a')
        self.q.enqueue('b')
        self.q.enqueue('c')
        self.assertEqual(self.q.peek(), 'c')
        self.assertEqual(self.q.dequeue(), 'c')
        self.assertEqual(self.q.dequeue(), 'b')
        self.assertEqual(self.q.dequeue(), 'a')

    def test2_peek_empty(self):
        self.assertIsNone(self.q.peek())

    def test3_len_and_bool(self):
        self.assertEqual(len(self.q), 0)
        self.assertFalse(self.q)
        self.q.enqueue(1)
        self.assertEqual(len(self.q), 1)
        self.assertTrue(self.q)

    def test4_contains_and_iter(self):
        self.q.enqueue('x')
        self.q.enqueue('y')
        self.assertIn('x', self.q)
        self.assertNotIn('z', self.q)
        self.assertEqual(list(self.q), ['x', 'y'])

    def test5_remove_if(self):
        for i in range(4):
            self.q.enqueue(i)
        self.q.remove_if(lambda e: e % 2 == 0)
        self.assertEqual(list(self.q), [1, 3])


class TestDSKeyQueue(unittest.TestCase):

    def test1_init_empty(self):
        q = DSKeyQueue()
        self.assertEqual(len(q), 0)
        self.assertFalse(q)
        self.assertIsNone(q.head)
        self.assertIsNone(q.tail)

    def test2_default_key_orders_ascending(self):
        q = DSKeyQueue()
        q.enqueue(3)
        q.enqueue(1)
        q.enqueue(2)
        self.assertEqual([q.dequeue() for _ in range(3)], [1, 2, 3])

    def test3_single_item(self):
        q = DSKeyQueue()
        q.enqueue(42)
        self.assertEqual(q.peek(), 42)
        self.assertEqual(q.dequeue(), 42)
        self.assertEqual(len(q), 0)

    def test4_min_priority_integers(self):
        q = DSKeyQueue(key=lambda x: x)
        for v in [5, 1, 3, 2, 4]:
            q.enqueue(v)
        self.assertEqual([q.dequeue() for _ in range(5)], [1, 2, 3, 4, 5])

    def test5_max_priority_negated_key(self):
        q = DSKeyQueue(key=lambda x: -x)
        for v in [5, 1, 3, 2, 4]:
            q.enqueue(v)
        self.assertEqual([q.dequeue() for _ in range(5)], [5, 4, 3, 2, 1])

    def test6_key_on_dict_field(self):
        q = DSKeyQueue(key=lambda item: item['priority'])
        q.enqueue({'name': 'low',  'priority': 10})
        q.enqueue({'name': 'high', 'priority': 1})
        q.enqueue({'name': 'mid',  'priority': 5})
        self.assertEqual(q.dequeue()['name'], 'high')
        self.assertEqual(q.dequeue()['name'], 'mid')
        self.assertEqual(q.dequeue()['name'], 'low')

    def test7_key_on_object_attribute(self):
        class Task:
            def __init__(self, name, prio):
                self.name = name
                self.prio = prio
        q = DSKeyQueue(key=lambda t: t.prio)
        q.enqueue(Task('c', 30))
        q.enqueue(Task('a', 10))
        q.enqueue(Task('b', 20))
        self.assertEqual(q.dequeue().name, 'a')
        self.assertEqual(q.dequeue().name, 'b')
        self.assertEqual(q.dequeue().name, 'c')

    def test8_equal_keys_stable_order(self):
        q = DSKeyQueue(key=lambda x: x[0])
        q.enqueue((1, 'first'))
        q.enqueue((1, 'second'))
        q.enqueue((1, 'third'))
        self.assertEqual(q.dequeue()[1], 'first')
        self.assertEqual(q.dequeue()[1], 'second')
        self.assertEqual(q.dequeue()[1], 'third')

    def test9_peek_does_not_remove(self):
        q = DSKeyQueue(key=lambda x: x)
        q.enqueue(5)
        q.enqueue(2)
        self.assertEqual(q.peek(), 2)
        self.assertEqual(len(q), 2)
        self.assertEqual(q.peek(), 2)

    def test10_peek_empty(self):
        self.assertIsNone(DSKeyQueue().peek())

    def test11_enqueue_returns_item(self):
        q = DSKeyQueue()
        obj = object()
        self.assertIs(q.enqueue(obj), obj)

    def test12_interleaved_operations(self):
        q = DSKeyQueue(key=lambda x: x)
        q.enqueue(4)
        q.enqueue(2)
        self.assertEqual(q.dequeue(), 2)
        q.enqueue(1)
        q.enqueue(3)
        self.assertEqual([q.dequeue() for _ in range(3)], [1, 3, 4])

    def test13_contains_and_iter(self):
        q = DSKeyQueue(key=lambda x: x)
        q.enqueue(10)
        q.enqueue(5)
        self.assertIn(5, q)
        self.assertNotIn(99, q)
        self.assertEqual(sorted(q), [5, 10])

    def test14_remove(self):
        q = DSKeyQueue(key=lambda x: x)
        q.enqueue(3)
        q.enqueue(1)
        q.enqueue(2)
        q.remove(1)
        self.assertEqual([q.dequeue() for _ in range(2)], [2, 3])

    def test15_remove_if(self):
        q = DSKeyQueue(key=lambda x: x)
        for v in [4, 1, 3, 2]:
            q.enqueue(v)
        q.remove_if(lambda e: e % 2 == 0)
        self.assertEqual([q.dequeue() for _ in range(2)], [1, 3])

    def test16_pop_at(self):
        q = DSKeyQueue(key=lambda x: x)
        for v in [3, 1, 2]:
            q.enqueue(v)
        self.assertEqual(q.pop_at(1), 2)
        self.assertEqual([q.dequeue() for _ in range(2)], [1, 3])

    def test17_len_and_bool(self):
        q = DSKeyQueue()
        self.assertFalse(q)
        q.enqueue(0)
        self.assertTrue(q)
        self.assertEqual(len(q), 1)


class TestDSResource(unittest.TestCase):

    def test1_init_valid(self):
        r = DSResource(amount=2, capacity=5)
        self.assertEqual(r.amount, 2)
        self.assertEqual(r.capacity, 5)

    def test2_init_invalid_amount_gt_capacity(self):
        with self.assertRaises(ValueError):
            DSResource(amount=6, capacity=5)

    def test3_put_get_nowait(self):
        r = DSResource(amount=1, capacity=3)
        self.assertEqual(r.put_n_nowait(2), 2)
        self.assertEqual(r.amount, 3)
        self.assertEqual(r.put_n_nowait(1), 0)  # full
        self.assertEqual(r.get_n_nowait(2), 2)
        self.assertEqual(r.amount, 1)
        self.assertEqual(r.get_n_nowait(2), 0)  # insufficient

    def test4_owner_mapping_updates_owner_attrs(self):
        owner = _Owner()
        r = DSResource(amount=2, capacity=4, owner=owner)
        self.assertEqual(owner.amount, 2)
        self.assertEqual(owner.capacity, 4)
        self.assertEqual(r.put_n_nowait(1), 1)
        self.assertEqual(owner.amount, 3)
        self.assertEqual(r.get_n_nowait(2), 2)
        self.assertEqual(owner.amount, 1)


class TestDSPriorityResource(unittest.TestCase):

    def test1_remember_and_held_amount(self):
        p = DSPriorityResource()
        p.remember_acquire('a', 3, 5)
        self.assertEqual(p.held_amount('a'), 3)
        self.assertEqual(p.holders_by_priority, {5: ['a']})

    def test2_same_owner_same_priority_accumulates_and_refreshes_recency(self):
        p = DSPriorityResource()
        p.remember_acquire('a', 1, 5)
        p.remember_acquire('b', 1, 5)
        p.remember_acquire('a', 2, 5)  # refresh recency -> 'a' should move to end
        self.assertEqual(p.held_amount('a'), 3)
        self.assertEqual(p.holders_by_priority[5], ['b', 'a'])

    def test3_better_priority_moves_bucket(self):
        p = DSPriorityResource()
        p.remember_acquire('a', 1, 7)
        p.remember_acquire('a', 2, 3)
        self.assertNotIn(7, p.holders_by_priority)
        self.assertEqual(p.holders_by_priority[3], ['a'])
        self.assertEqual(p.holders_by_owner['a'][0], 3)  # amount
        self.assertEqual(p.holders_by_owner['a'][1], 3)  # priority

    def test4_set_holder_amount_zero_removes_owner_and_bucket(self):
        p = DSPriorityResource()
        p.remember_acquire('a', 2, 4)
        p.set_holder_amount('a', 0)
        self.assertEqual(p.held_amount('a'), 0)
        self.assertNotIn('a', p.holders_by_owner)
        self.assertNotIn(4, p.holders_by_priority)

    def test5_consume_reclaimed_release(self):
        p = DSPriorityResource()
        p.reclaimed['a'] = 5
        self.assertEqual(p.consume_reclaimed_release('a', 3), 0)
        self.assertEqual(p.reclaimed['a'], 2)
        self.assertEqual(p.consume_reclaimed_release('a', 3), 1)
        self.assertNotIn('a', p.reclaimed)
        self.assertEqual(p.consume_reclaimed_release('a', 3), 3)


class TestDSPriorityPreemption(unittest.TestCase):

    def test1_reclaim_order_and_amount(self):
        p = DSPriorityResource()
        # priority 10 bucket insertion order: b then c (newest c)
        p.remember_acquire('a', 2, 5)
        p.remember_acquire('b', 3, 10)
        p.remember_acquire('c', 4, 10)

        pre = DSPriorityPreemption(p)
        on_take = []
        on_preempted = []
        on_reclaimed = []

        released = pre.reclaim_from_victims(
            need=5,
            requester='req',
            req_priority=1,
            on_take=lambda n: on_take.append(n),
            on_preempted=lambda owner, prio, n: on_preempted.append((owner, prio, n)),
            on_reclaimed=lambda n: on_reclaimed.append(n),
        )

        self.assertEqual(released, 5)
        self.assertEqual(on_take, [4, 1])
        self.assertEqual(on_preempted, [('c', 10, 4), ('b', 10, 1)])
        self.assertEqual(on_reclaimed, [5])
        self.assertEqual(p.held_amount('a'), 2)
        self.assertEqual(p.held_amount('b'), 2)
        self.assertEqual(p.held_amount('c'), 0)
        self.assertEqual(p.reclaimed['c'], 4)
        self.assertEqual(p.reclaimed['b'], 1)

    def test2_skips_requester_and_equal_or_better_priorities(self):
        p = DSPriorityResource()
        p.remember_acquire('req', 5, 8)
        p.remember_acquire('same', 5, 8)
        p.remember_acquire('better', 5, 2)
        p.remember_acquire('worse', 5, 9)
        pre = DSPriorityPreemption(p)

        preempted = []
        released = pre.reclaim_from_victims(
            need=4,
            requester='req',
            req_priority=8,
            on_take=lambda n: None,
            on_preempted=lambda owner, prio, n: preempted.append((owner, prio, n)),
        )
        self.assertEqual(released, 4)
        self.assertEqual(preempted, [('worse', 9, 4)])
        self.assertEqual(p.held_amount('req'), 5)
        self.assertEqual(p.held_amount('same'), 5)
        self.assertEqual(p.held_amount('better'), 5)
        self.assertEqual(p.held_amount('worse'), 1)

    def test3_noop_for_nonpositive_need(self):
        p = DSPriorityResource()
        p.remember_acquire('a', 3, 9)
        pre = DSPriorityPreemption(p)

        called = []
        released = pre.reclaim_from_victims(
            need=0,
            requester='req',
            req_priority=1,
            on_take=lambda n: called.append('take'),
            on_preempted=lambda owner, prio, n: called.append('preempt'),
            on_reclaimed=lambda n: called.append('reclaimed'),
        )
        self.assertEqual(released, 0)
        self.assertEqual(called, [])
        self.assertEqual(p.held_amount('a'), 3)
