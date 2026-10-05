import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from registration_api import cors_middleware, registration_info


class RegistrationNetworkTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = SimpleNamespace(registration_token_owner=AsyncMock(return_value=(55, 77)))
        app = web.Application(middlewares=[cors_middleware])
        app['db'] = self.db
        app.router.add_get('/api/registration/{token}', registration_info)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()
        self.origin = {'Origin': 'https://loun-sys.github.io'}
        self.env = patch.dict('os.environ', {'TYRANNY_WEB_ORIGIN': 'https://loun-sys.github.io'})
        self.env.start()

    async def asyncTearDown(self):
        await self.client.close()
        self.env.stop()

    async def test_valid_link_loads_complete_constructor_with_cors(self):
        response = await self.client.get('/api/registration/test-only', headers=self.origin)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers['Access-Control-Allow-Origin'], self.origin['Origin'])
        data = await response.json()
        self.assertTrue(data['ok'])
        self.assertEqual(len(data['config']['backgrounds']), 7)
        self.assertEqual(len(data['config']['specializations']), 10)
        self.assertEqual(len(data['config']['skills']), 22)

    async def test_invalid_link_returns_readable_gone_not_network_failure(self):
        self.db.registration_token_owner.return_value = None
        response = await self.client.get('/api/registration/test-only', headers=self.origin)
        self.assertEqual(response.status, 410)
        self.assertEqual(response.headers['Access-Control-Allow-Origin'], self.origin['Origin'])
        self.assertIn('истекла', (await response.json())['error'])

    async def test_internal_error_keeps_cors_and_does_not_expose_details(self):
        self.db.registration_token_owner.side_effect = RuntimeError('private database diagnostic')
        with patch('registration_api.logging.getLogger') as logger:
            response = await self.client.get('/api/registration/test-only', headers=self.origin)
        logger.return_value.exception.assert_called_once()
        self.assertEqual(response.status, 500)
        self.assertEqual(response.headers['Access-Control-Allow-Origin'], self.origin['Origin'])
        data = await response.json()
        self.assertFalse(data['ok'])
        self.assertIn('Ошибка сервера', data['error'])
        self.assertNotIn('private', data['error'])

    async def test_options_and_errors_do_not_expand_allowed_origins(self):
        headers = {**self.origin, 'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'content-type'}
        response = await self.client.options('/api/registration/test-only', headers=headers)
        self.assertEqual(response.status, 204)
        self.assertIn('POST', response.headers['Access-Control-Allow-Methods'])
        self.db.registration_token_owner.assert_not_called()
        self.db.registration_token_owner.side_effect = RuntimeError('test failure')
        with patch('registration_api.logging.getLogger'):
            response = await self.client.get('/api/registration/test-only', headers={'Origin': 'https://untrusted.example'})
        self.assertEqual(response.status, 500)
        self.assertNotIn('Access-Control-Allow-Origin', response.headers)


if __name__ == '__main__':
    unittest.main()
