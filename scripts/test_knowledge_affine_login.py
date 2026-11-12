"""Authentication contract tests: private cookie storage without password persistence."""
import contextlib
from email.message import Message
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import Mock

spec=importlib.util.spec_from_file_location('affine_login',Path(__file__).with_name('knowledge-affine-login.py'))
login=importlib.util.module_from_spec(spec)
spec.loader.exec_module(login)


class LoginTests(unittest.TestCase):
    def test_signin_requires_password_and_never_sends_magic_link(self):
        opener=Mock()
        with self.assertRaises(ValueError): login.sign_in('http://127.0.0.1:3010','owner@example.test','',opener)
        opener.open.assert_not_called()

    def test_credential_redirect_destinations_are_rejected_before_request(self):
        opener=Mock()
        with self.assertRaises(ValueError): login.sign_in('https://evil.test','owner@example.test','secret',opener)
        opener.open.assert_not_called()
        self.assertIsNone(login.NoRedirect().redirect_request(None,None,302,None,{},'https://evil.test'))

    def test_normal_cookie_session_verified_and_password_not_retained(self):
        response=Mock()
        response.headers=Message()
        response.headers.add_header('Set-Cookie','session=sensitive; HttpOnly; Path=/')
        response.headers.add_header('Set-Cookie','user=owner; Path=/')
        check=Mock()
        check.read.return_value=b'{"user":{"id":"owner"}}'
        opener=Mock()
        opener.open.side_effect=[contextlib.nullcontext(response),contextlib.nullcontext(check)]
        session=login.sign_in('http://127.0.0.1:3010','owner@example.test','secret',opener)
        self.assertNotIn('secret',json.dumps(session))
        self.assertIn('session=sensitive',session['cookie'])
        first=opener.open.call_args_list[0].args[0]
        self.assertEqual(json.loads(first.data)['password'],'secret')
        self.assertEqual(first.method,'POST')
        self.assertEqual(opener.open.call_args_list[1].args[0].get_method(),'GET')

    def test_empty_authenticated_identity_is_rejected(self):
        response=Mock()
        response.headers=Message()
        response.headers.add_header('Set-Cookie','session=sensitive; Path=/')
        check=Mock();check.read.return_value=b'{"user":null}'
        opener=Mock();opener.open.side_effect=[contextlib.nullcontext(response),contextlib.nullcontext(check)]
        with self.assertRaisesRegex(ValueError,'verification_failed'):
            login.sign_in('http://127.0.0.1:3010','owner@example.test','secret',opener)


if __name__=='__main__':
    unittest.main()
