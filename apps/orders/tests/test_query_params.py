"""Query-string parsing helpers used by the order views."""
from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.orders.views import query_params as qp


def req(**params):
    return Request(APIRequestFactory().get('/', params))


class ParseIntTests(SimpleTestCase):

    def test_default_when_missing(self):
        self.assertEqual(qp.parse_int(req(), 'x', default=7), 7)

    def test_parses_value(self):
        self.assertEqual(qp.parse_int(req(x='5'), 'x'), 5)

    def test_rejects_non_integer(self):
        with self.assertRaises(ValidationError):
            qp.parse_int(req(x='abc'), 'x')

    def test_enforces_bounds(self):
        with self.assertRaises(ValidationError):
            qp.parse_int(req(x='0'), 'x', minimum=1)
        with self.assertRaises(ValidationError):
            qp.parse_int(req(x='101'), 'x', maximum=100)
        self.assertEqual(qp.parse_int(req(x='100'), 'x', maximum=100), 100)


class ParseBoolTests(SimpleTestCase):

    def test_truthy_and_falsy_spellings(self):
        for raw in ('true', 'True', '1', 'yes'):
            self.assertIs(qp.parse_bool(req(b=raw), 'b'), True, raw)
        for raw in ('false', 'FALSE', '0', 'no'):
            self.assertIs(qp.parse_bool(req(b=raw), 'b'), False, raw)

    def test_missing_returns_default(self):
        self.assertIsNone(qp.parse_bool(req(), 'b'))
        self.assertIs(qp.parse_bool(req(), 'b', default=True), True)

    def test_invalid_raises(self):
        with self.assertRaises(ValidationError):
            qp.parse_bool(req(b='maybe'), 'b')

    def test_is_indoor(self):
        self.assertIsNone(qp.parse_is_indoor(req()))
        self.assertIs(qp.parse_is_indoor(req(is_indoor='true')), True)
        self.assertIs(qp.parse_is_indoor(req(is_indoor='no')), False)
        with self.assertRaises(ValidationError):
            qp.parse_is_indoor(req(is_indoor='x'))


class ParseScopeTests(SimpleTestCase):

    def test_default_and_values(self):
        self.assertEqual(qp.parse_scope(req()), 'all')
        self.assertEqual(qp.parse_scope(req(scope='VIP')), 'vip')
        self.assertEqual(qp.parse_scope(req(scope='normal')), 'normal')

    def test_invalid(self):
        with self.assertRaises(ValidationError):
            qp.parse_scope(req(scope='everything'))


class ParseStatusesTests(SimpleTestCase):

    def test_missing_is_none(self):
        self.assertIsNone(qp.parse_statuses(req()))

    def test_comma_separated(self):
        self.assertEqual(qp.parse_statuses(req(status='pending, done')), ['pending', 'done'])

    def test_invalid_value(self):
        with self.assertRaises(ValidationError) as ctx:
            qp.parse_statuses(req(status='pending,bogus'))
        self.assertIn('bogus', str(ctx.exception.detail))

    def test_empty_value(self):
        with self.assertRaises(ValidationError):
            qp.parse_statuses(req(status=' , '))


class PagingAndLimitTests(SimpleTestCase):

    def test_limit(self):
        self.assertIsNone(qp.parse_limit(req()))
        self.assertEqual(qp.parse_limit(req(limit='3')), 3)
        for bad in ('0', '-1', 'x'):
            with self.assertRaises(ValidationError, msg=bad):
                qp.parse_limit(req(limit=bad))

    def test_window_size_page_and_batch_limit_defaults(self):
        r = req()
        self.assertEqual(qp.parse_window_size(r), 10)
        self.assertEqual(qp.parse_page(r), 1)
        self.assertEqual(qp.parse_page_size(r), 20)
        self.assertIsNone(qp.parse_batch_limit(r))

    def test_page_size_capped_at_100(self):
        with self.assertRaises(ValidationError):
            qp.parse_page_size(req(page_size='101'))

    def test_window_size_must_be_positive(self):
        with self.assertRaises(ValidationError):
            qp.parse_window_size(req(window_size='0'))


class ParseOrderingTests(SimpleTestCase):
    ALLOWED = {'created_at', 'priority_score'}

    def test_none_when_missing(self):
        self.assertIsNone(qp.parse_ordering(req(), allowed=self.ALLOWED))

    def test_valid_with_descending_prefix(self):
        self.assertEqual(
            qp.parse_ordering(req(ordering='-created_at,priority_score'), allowed=self.ALLOWED),
            '-created_at,priority_score',
        )

    def test_unknown_field_rejected(self):
        with self.assertRaises(ValidationError):
            qp.parse_ordering(req(ordering='password'), allowed=self.ALLOWED)
