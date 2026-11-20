"""
Tests for the users app: authentication, role-based access control,
restaurant profiles and cashier management.

Run with the in-memory SQLite settings (no Postgres needed):
    python -m django test apps.users --settings=config.settings.test
"""
from decimal import Decimal

from rest_framework.test import APIClient, APITestCase

from apps.restaurants.models import Category, MenuItem
from apps.users.helpers.constants import UserRole
from apps.users.models import CashierProfile, RestaurantProfile, User

PASSWORD = 'pass12345'

REGISTER_URL = '/api/v1/auth/register/'
LOGIN_URL = '/api/v1/auth/login/'
REFRESH_URL = '/api/v1/auth/refresh/'
LOGOUT_URL = '/api/v1/auth/logout/'
ME_URL = '/api/v1/users/me/'
USERS_URL = '/api/v1/users/'
CASHIERS_URL = '/api/v1/cashiers/'
VIP_BULK_URL = '/api/v1/cashiers/set-vip-permission/'
PROFILE_URL = '/api/v1/restaurant-profiles/'
ORDERS_URL = '/api/v1/orders/'


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
class UserTestMixin:
    @staticmethod
    def make_user(username, role, **extra):
        return User.objects.create_user(
            username=username,
            email=extra.pop('email', f'{username}@example.com'),
            password=PASSWORD,
            role=role,
            **extra,
        )

    @classmethod
    def make_restaurant(cls, suffix):
        owner = cls.make_user(f'owner_{suffix}', UserRole.RESTAURANT)
        profile = RestaurantProfile.objects.create(user=owner, restaurant_name=f'Resto {suffix}')
        return owner, profile

    @classmethod
    def make_cashier(cls, suffix, restaurant, can_set_vip=False, is_active=True):
        user = cls.make_user(f'cashier_{suffix}', UserRole.CASHIER)
        profile = CashierProfile.objects.create(
            user=user, restaurant=restaurant, can_set_vip=can_set_vip, is_active=is_active,
        )
        return user, profile

    @staticmethod
    def make_menu_item(restaurant, name='Burger', prep_time=5):
        category, _ = Category.objects.get_or_create(restaurant=restaurant, name='Main', defaults={'priority': 3})
        return MenuItem.objects.create(
            restaurant=restaurant, category=category, name=name,
            prep_time=prep_time, price=Decimal('10.00'),
        )

    @staticmethod
    def client_for(user):
        # Reload from the DB so cached reverse relations (e.g. cashier_profile)
        # are fresh, exactly like a real request where the user is loaded per call.
        client = APIClient()
        client.force_authenticate(user=User.objects.get(pk=user.pk))
        return client


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
class RegistrationTests(UserTestMixin, APITestCase):

    def _payload(self, **overrides):
        data = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password': PASSWORD,
            'confirm_password': PASSWORD,
            'role': UserRole.CUSTOMER,
        }
        data.update(overrides)
        return data

    def test_register_customer_succeeds(self):
        resp = self.client.post(REGISTER_URL, self._payload(), format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['user']['role'], UserRole.CUSTOMER)
        self.assertTrue(User.objects.filter(username='newuser').exists())

    def test_register_restaurant_creates_profile_atomically(self):
        payload = self._payload(username='chef', email='chef@example.com',
                                role=UserRole.RESTAURANT, restaurant_name='Chef Place')
        resp = self.client.post(REGISTER_URL, payload, format='json')
        self.assertEqual(resp.status_code, 201)
        user = User.objects.get(username='chef')
        self.assertEqual(user.restaurant_profile.restaurant_name, 'Chef Place')

    def test_register_restaurant_requires_restaurant_name(self):
        payload = self._payload(role=UserRole.RESTAURANT)
        resp = self.client.post(REGISTER_URL, payload, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('restaurant_name', resp.data)

    def test_register_cannot_create_privileged_roles(self):
        """Privilege-escalation guard: admin/cashier can't be self-registered."""
        for role in (UserRole.ADMIN, UserRole.CASHIER):
            with self.subTest(role=role):
                payload = self._payload(username=f'x_{role}', email=f'x_{role}@example.com', role=role)
                resp = self.client.post(REGISTER_URL, payload, format='json')
                self.assertEqual(resp.status_code, 400)
                self.assertFalse(User.objects.filter(username=f'x_{role}').exists())

    def test_register_rejects_password_mismatch(self):
        resp = self.client.post(REGISTER_URL, self._payload(confirm_password='different1'), format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('confirm_password', resp.data)

    def test_register_rejects_short_password(self):
        resp = self.client.post(REGISTER_URL, self._payload(password='short', confirm_password='short'), format='json')
        self.assertEqual(resp.status_code, 400)

    def test_register_rejects_at_sign_in_username(self):
        resp = self.client.post(REGISTER_URL, self._payload(username='bad@name'), format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('username', resp.data)

    def test_register_rejects_duplicate_email(self):
        self.make_user('existing', UserRole.CUSTOMER, email='dup@example.com')
        resp = self.client.post(REGISTER_URL, self._payload(email='dup@example.com'), format='json')
        self.assertEqual(resp.status_code, 400)

    def test_duplicate_restaurant_name_rolls_back_user_creation(self):
        """transaction.atomic: a failed profile insert must not leave an orphan user."""
        self.make_restaurant('taken')  # restaurant_name = 'Resto taken'
        payload = self._payload(username='second', email='second@example.com',
                                role=UserRole.RESTAURANT, restaurant_name='Resto taken')
        resp = self.client.post(REGISTER_URL, payload, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(User.objects.filter(username='second').exists())


# ---------------------------------------------------------------------------
# Login / refresh / logout (JWT lifecycle)
# ---------------------------------------------------------------------------
class AuthLifecycleTests(UserTestMixin, APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = cls.make_user('alice', UserRole.CUSTOMER, email='alice@example.com')

    def _login(self, identifier='alice', password=PASSWORD):
        return self.client.post(
            LOGIN_URL, {'username_or_email': identifier, 'password': password}, format='json')

    def test_login_with_username(self):
        resp = self._login('alice')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('access', resp.data)
        self.assertIn('refresh', resp.data)
        self.assertEqual(resp.data['user']['role'], UserRole.CUSTOMER)

    def test_login_with_email(self):
        resp = self._login('alice@example.com')
        self.assertEqual(resp.status_code, 200)

    def test_login_sets_httponly_refresh_cookie(self):
        resp = self._login()
        cookie = resp.cookies['refresh_token']
        self.assertTrue(cookie['httponly'])

    def test_login_wrong_password_is_401(self):
        self.assertEqual(self._login(password='wrong-pass').status_code, 401)

    def test_login_unknown_email_is_401(self):
        self.assertEqual(self._login('ghost@example.com').status_code, 401)

    def test_access_token_grants_access_to_protected_endpoint(self):
        access = self._login().data['access']
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        resp = client.get(ME_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['username'], 'alice')

    def test_protected_endpoint_without_token_is_401(self):
        self.assertEqual(APIClient().get(ME_URL).status_code, 401)

    def test_refresh_rotates_token_and_old_one_is_blacklisted(self):
        old_refresh = self._login().data['refresh']
        client = APIClient()
        first = client.post(REFRESH_URL, {'refresh': old_refresh}, format='json')
        self.assertEqual(first.status_code, 200)
        self.assertIn('access', first.data)
        self.assertNotEqual(first.data['refresh'], old_refresh)
        # Replaying the already-rotated token must fail (reuse detection).
        replay = client.post(REFRESH_URL, {'refresh': old_refresh}, format='json')
        self.assertEqual(replay.status_code, 401)

    def test_refresh_works_from_cookie(self):
        self._login()  # APIClient stores the refresh_token cookie
        resp = self.client.post(REFRESH_URL, {}, format='json')
        self.assertEqual(resp.status_code, 200)

    def test_refresh_with_garbage_token_is_401_not_500(self):
        resp = APIClient().post(REFRESH_URL, {'refresh': 'not-a-jwt'}, format='json')
        self.assertEqual(resp.status_code, 401)

    def test_refresh_without_token_is_401(self):
        self.assertEqual(APIClient().post(REFRESH_URL, {}, format='json').status_code, 401)

    def test_logout_blacklists_refresh_token(self):
        data = self._login().data
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {data['access']}")
        self.assertEqual(client.post(LOGOUT_URL, {'refresh_token': data['refresh']}, format='json').status_code, 200)
        # The refresh token can no longer be exchanged.
        after = APIClient().post(REFRESH_URL, {'refresh': data['refresh']}, format='json')
        self.assertEqual(after.status_code, 401)

    def test_logout_requires_authentication(self):
        self.assertEqual(APIClient().post(LOGOUT_URL, {'refresh_token': 'x'}, format='json').status_code, 401)


# ---------------------------------------------------------------------------
# Users endpoints + role-based access control
# ---------------------------------------------------------------------------
class UserAccessControlTests(UserTestMixin, APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.admin = cls.make_user('admin1', UserRole.ADMIN)
        cls.customer = cls.make_user('cust1', UserRole.CUSTOMER)
        cls.other_customer = cls.make_user('cust2', UserRole.CUSTOMER)
        cls.owner, cls.restaurant = cls.make_restaurant('acl')

    def test_only_admin_can_list_users(self):
        self.assertEqual(self.client_for(self.admin).get(USERS_URL).status_code, 200)
        for user in (self.customer, self.owner):
            with self.subTest(role=user.role):
                self.assertEqual(self.client_for(user).get(USERS_URL).status_code, 403)
        self.assertEqual(APIClient().get(USERS_URL).status_code, 401)

    def test_me_returns_own_profile(self):
        resp = self.client_for(self.owner).get(ME_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['restaurant_profile']['restaurant_name'], 'Resto acl')

    def test_admin_can_read_another_user_via_user_id(self):
        resp = self.client_for(self.admin).get(ME_URL, {'user_id': str(self.customer.id)})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['username'], 'cust1')

    def test_admin_user_id_for_unknown_user_is_404(self):
        resp = self.client_for(self.admin).get(
            ME_URL, {'user_id': '00000000-0000-0000-0000-000000000000'})
        self.assertEqual(resp.status_code, 404)

    def test_non_admin_cannot_read_others_by_user_id(self):
        """?user_id must be ignored for non-admins (horizontal escalation guard)."""
        resp = self.client_for(self.customer).get(ME_URL, {'user_id': str(self.other_customer.id)})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['username'], 'cust1')

    def test_non_admin_cannot_modify_others_by_user_id(self):
        resp = self.client_for(self.customer).patch(
            ME_URL + f'?user_id={self.other_customer.id}', {'phone_number': '123'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.other_customer.refresh_from_db()
        self.customer.refresh_from_db()
        self.assertIsNone(self.other_customer.phone_number)
        self.assertEqual(self.customer.phone_number, '123')

    def test_user_cannot_change_own_role(self):
        """Mass-assignment guard: role is not writable through the update endpoint."""
        resp = self.client_for(self.customer).patch(ME_URL, {'role': UserRole.ADMIN}, format='json')
        self.assertIn(resp.status_code, (200, 400))
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.role, UserRole.CUSTOMER)

    def test_update_rejects_duplicate_email(self):
        resp = self.client_for(self.customer).patch(ME_URL, {'email': self.other_customer.email}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_patch_updates_allowed_fields(self):
        resp = self.client_for(self.customer).patch(ME_URL, {'phone_number': '0100000000'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.phone_number, '0100000000')


# ---------------------------------------------------------------------------
# Restaurant profile (owner vs admin endpoints)
# ---------------------------------------------------------------------------
class RestaurantProfileAccessTests(UserTestMixin, APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.admin = cls.make_user('admin_p', UserRole.ADMIN)
        cls.customer = cls.make_user('cust_p', UserRole.CUSTOMER)
        cls.owner, cls.restaurant = cls.make_restaurant('p1')
        cls.other_owner, cls.other_restaurant = cls.make_restaurant('p2')

    def test_owner_reads_and_updates_own_profile(self):
        client = self.client_for(self.owner)
        self.assertEqual(client.get(PROFILE_URL).data['restaurant_name'], 'Resto p1')
        resp = client.patch(PROFILE_URL, {'address': '1 Nile St'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.restaurant.refresh_from_db()
        self.assertEqual(self.restaurant.address, '1 Nile St')

    def test_customer_cannot_access_owner_profile_endpoint(self):
        self.assertEqual(self.client_for(self.customer).get(PROFILE_URL).status_code, 403)

    def test_owner_cannot_use_admin_profile_endpoint(self):
        url = f'{PROFILE_URL}{self.other_owner.id}/'
        self.assertEqual(self.client_for(self.owner).get(url).status_code, 403)

    def test_admin_can_manage_any_profile(self):
        url = f'{PROFILE_URL}{self.other_owner.id}/'
        client = self.client_for(self.admin)
        self.assertEqual(client.get(url).status_code, 200)
        self.assertEqual(client.patch(url, {'is_active': False}, format='json').status_code, 200)
        self.other_restaurant.refresh_from_db()
        self.assertFalse(self.other_restaurant.is_active)

    def test_admin_profile_lookup_for_user_without_profile_is_404(self):
        url = f'{PROFILE_URL}{self.customer.id}/'
        self.assertEqual(self.client_for(self.admin).get(url).status_code, 404)


# ---------------------------------------------------------------------------
# Cashier management
# ---------------------------------------------------------------------------
class CashierManagementTests(UserTestMixin, APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.owner, cls.restaurant = cls.make_restaurant('c1')
        cls.other_owner, cls.other_restaurant = cls.make_restaurant('c2')
        cls.cashier_user, cls.cashier = cls.make_cashier('a', cls.restaurant)
        cls.foreign_user, cls.foreign_cashier = cls.make_cashier('b', cls.other_restaurant)
        cls.customer = cls.make_user('cust_c', UserRole.CUSTOMER)

    def _new_cashier(self, **overrides):
        data = {'username': 'newcashier', 'email': 'newcashier@example.com', 'password': PASSWORD}
        data.update(overrides)
        return data

    def test_owner_creates_cashier_linked_to_own_restaurant(self):
        resp = self.client_for(self.owner).post(CASHIERS_URL, self._new_cashier(), format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['role'], UserRole.CASHIER)
        profile = CashierProfile.objects.get(user__username='newcashier')
        self.assertEqual(profile.restaurant_id, self.restaurant.id)
        self.assertFalse(profile.can_set_vip)

    def test_created_cashier_can_log_in(self):
        self.client_for(self.owner).post(CASHIERS_URL, self._new_cashier(), format='json')
        resp = APIClient().post(
            LOGIN_URL, {'username_or_email': 'newcashier', 'password': PASSWORD}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['user']['role'], UserRole.CASHIER)

    def test_duplicate_username_and_email_rejected(self):
        client = self.client_for(self.owner)
        self.assertEqual(client.post(CASHIERS_URL, self._new_cashier(username='cashier_a'), format='json').status_code, 400)
        self.assertEqual(client.post(CASHIERS_URL, self._new_cashier(email=self.cashier_user.email), format='json').status_code, 400)

    def test_only_restaurant_owner_can_manage_cashiers(self):
        for user in (self.cashier_user, self.customer):
            with self.subTest(role=user.role):
                client = self.client_for(user)
                self.assertEqual(client.get(CASHIERS_URL).status_code, 403)
                self.assertEqual(client.post(CASHIERS_URL, self._new_cashier(), format='json').status_code, 403)

    def test_owner_lists_only_own_cashiers(self):
        resp = self.client_for(self.owner).get(CASHIERS_URL)
        self.assertEqual([c['username'] for c in resp.data['results']], ['cashier_a'])

    def test_owner_cannot_see_or_edit_another_restaurants_cashier(self):
        """Tenant isolation: a foreign cashier profile id behaves like it doesn't exist."""
        url = f'{CASHIERS_URL}{self.foreign_cashier.id}/'
        client = self.client_for(self.owner)
        self.assertEqual(client.get(url).status_code, 404)
        self.assertEqual(client.patch(url, {'is_active': False}, format='json').status_code, 404)
        self.foreign_cashier.refresh_from_db()
        self.assertTrue(self.foreign_cashier.is_active)

    def test_owner_toggles_cashier_flags(self):
        url = f'{CASHIERS_URL}{self.cashier.id}/'
        resp = self.client_for(self.owner).patch(url, {'can_set_vip': True, 'is_active': False}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.cashier.refresh_from_db()
        self.assertTrue(self.cashier.can_set_vip)
        self.assertFalse(self.cashier.is_active)

    def test_bulk_vip_permission_only_touches_own_restaurant(self):
        resp = self.client_for(self.owner).post(VIP_BULK_URL, {'can_set_vip': True}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['updated'], 1)
        self.cashier.refresh_from_db()
        self.foreign_cashier.refresh_from_db()
        self.assertTrue(self.cashier.can_set_vip)
        self.assertFalse(self.foreign_cashier.can_set_vip)


# ---------------------------------------------------------------------------
# Cashier permissions in the orders API (cross-app RBAC integration)
# ---------------------------------------------------------------------------
class StaffOrderPermissionTests(UserTestMixin, APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.owner, cls.restaurant = cls.make_restaurant('o1')
        cls.other_owner, cls.other_restaurant = cls.make_restaurant('o2')
        cls.item = cls.make_menu_item(cls.restaurant)
        cls.other_item = cls.make_menu_item(cls.other_restaurant)
        cls.plain_user, cls.plain = cls.make_cashier('plain', cls.restaurant, can_set_vip=False)
        cls.vip_user, cls.vip = cls.make_cashier('vip', cls.restaurant, can_set_vip=True)
        cls.inactive_user, _ = cls.make_cashier('off', cls.restaurant, is_active=False)
        cls.customer = cls.make_user('cust_o', UserRole.CUSTOMER)

    def _order_payload(self, special=False):
        return {'special_flag': special, 'order_items': [{'menu_item': str(self.item.id), 'quantity': 2}]}

    def test_cashier_can_create_normal_order(self):
        resp = self.client_for(self.plain_user).post(ORDERS_URL, self._order_payload(), format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['created_by']['username'], 'cashier_plain')

    def test_cashier_without_permission_cannot_set_vip(self):
        resp = self.client_for(self.plain_user).post(ORDERS_URL, self._order_payload(special=True), format='json')
        self.assertEqual(resp.status_code, 400)

    def test_cashier_with_permission_can_set_vip(self):
        resp = self.client_for(self.vip_user).post(ORDERS_URL, self._order_payload(special=True), format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.data['special_flag'])

    def test_owner_can_always_set_vip(self):
        resp = self.client_for(self.owner).post(ORDERS_URL, self._order_payload(special=True), format='json')
        self.assertEqual(resp.status_code, 201)

    def test_revoking_vip_permission_takes_effect_immediately(self):
        self.client_for(self.owner).patch(
            f'{CASHIERS_URL}{self.vip.id}/', {'can_set_vip': False}, format='json')
        resp = self.client_for(self.vip_user).post(ORDERS_URL, self._order_payload(special=True), format='json')
        self.assertEqual(resp.status_code, 400)

    def test_deactivated_cashier_loses_access(self):
        self.assertEqual(self.client_for(self.inactive_user).get(ORDERS_URL).status_code, 403)

    def test_customer_cannot_use_staff_order_endpoints(self):
        self.assertEqual(self.client_for(self.customer).get(ORDERS_URL).status_code, 403)

    def test_staff_cannot_read_another_restaurants_order(self):
        created = self.client_for(self.other_owner).post(
            ORDERS_URL,
            {'order_items': [{'menu_item': str(self.other_item.id), 'quantity': 1}]},
            format='json',
        )
        self.assertEqual(created.status_code, 201)
        resp = self.client_for(self.plain_user).get(f"{ORDERS_URL}{created.data['id']}/")
        self.assertEqual(resp.status_code, 404)
