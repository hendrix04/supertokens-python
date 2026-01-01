# Copyright (c) 2021, VRAI Labs and/or its affiliates. All rights reserved.
#
# This software is licensed under the Apache License, Version 2.0 (the
# "License") as published by the Apache Software Foundation.
#
# You may not use this file except in compliance with the License. You may
# obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
import json
from typing import Any, Dict, Optional, Union

from quart import Quart, request, Response
from pytest import fixture, mark
from supertokens_python import InputAppInfo, SupertokensConfig, init
from supertokens_python.framework import BaseRequest
from supertokens_python.framework.quart import Middleware
from supertokens_python.recipe import session, emailpassword, thirdparty
from supertokens_python.recipe.dashboard import DashboardRecipe, InputOverrideConfig
from supertokens_python.recipe.dashboard.interfaces import RecipeInterface
from supertokens_python.recipe.dashboard.utils import DashboardConfig
from supertokens_python.recipe.passwordless import ContactConfig, PasswordlessRecipe
from supertokens_python.recipe.session import SessionContainer
from supertokens_python.recipe.session.asyncio import (
    create_new_session,
    get_session,
    refresh_session,
)
from supertokens_python.recipe.session.framework.quart import verify_session
from supertokens_python.recipe.session.interfaces import APIInterface
from supertokens_python.types import RecipeUserId
from supertokens_python.utils import is_version_gte
from supertokens_python.querier import Querier

from tests.Quart.utils import extract_all_cookies
from tests.utils import (
    TEST_DRIVER_CONFIG_ACCESS_TOKEN_PATH,
    TEST_DRIVER_CONFIG_COOKIE_DOMAIN,
    TEST_DRIVER_CONFIG_COOKIE_SAME_SITE,
    TEST_DRIVER_CONFIG_REFRESH_TOKEN_PATH,
    create_users,
    get_new_core_app_url,
)


class QuartTestClient:
    def __init__(self, app):
        self.client = app.test_client()

    async def get(self, url, **kwargs):
        self.client.cookie_jar.clear()
        return await self.client.get(url, **kwargs)

    async def post(self, url, **kwargs):
        self.client.cookie_jar.clear()
        return await self.client.post(url, **kwargs)

    async def options(self, url, **kwargs):
        self.client.cookie_jar.clear()
        return await self.client.options(url, **kwargs)


@fixture(scope="function")
async def driver_config_client() -> QuartTestClient:
    app = Quart(__name__)
    Middleware(app)

    @app.route("/login", methods=["GET"])
    async def login():
        user_id = "userId"
        await create_new_session(request, "public", RecipeUserId(user_id), {}, {})
        return {"userId": user_id}

    @app.route("/refresh", methods=["POST"])
    async def custom_refresh():
        await refresh_session(request)
        return {}

    @app.route("/info", methods=["GET"])
    async def info_get():
        await get_session(request, True)
        return {}

    @app.route("/custom/info", methods=["GET"])
    async def custom_info():
        return {}

    @app.route("/custom/handle", methods=["OPTIONS"])
    async def custom_handle_options():
        return {"method": "option"}

    @app.route("/handle", methods=["GET"])
    async def handle_get():
        session: Union[None, SessionContainer] = await get_session(request, True)
        if session is None:
            raise Exception("Should never come here")
        return {"s": session.get_handle()}

    @app.route("/handle-session-optional", methods=["GET"])
    @verify_session(session_required=False)
    async def handle_get_optional():
        session: Optional[SessionContainer] = None
        from quart import g
        if hasattr(g, "supertokens"):
            session = g.supertokens

        if session is None:
            return {"s": "empty session"}
        return {"s": session.get_handle()}

    @app.route("/logout", methods=["POST"])
    async def custom_logout():
        session: Union[None, SessionContainer] = await get_session(request, True)
        if session is None:
            raise Exception("Should never come here")
        await session.revoke_session()
        return {}

    @app.route("/create", methods=["POST"])
    async def _create():
        await create_new_session(request, "public", RecipeUserId("userId"), {}, {})
        return ""

    return QuartTestClient(app)


def apis_override_session(param: APIInterface):
    param.disable_refresh_post = True
    return param


@mark.asyncio
async def test_login_refresh(driver_config_client: QuartTestClient):
    init(
        supertokens_config=SupertokensConfig(get_new_core_app_url()),
        app_info=InputAppInfo(
            app_name="SuperTokens Demo",
            api_domain="http://api.supertokens.io",
            website_domain="http://supertokens.io",
            api_base_path="/auth",
        ),
        framework="quart",
        recipe_list=[
            session.init(
                anti_csrf="VIA_TOKEN",
                cookie_domain="supertokens.io",
                get_token_transfer_method=lambda _, __, ___: "cookie",
                override=session.InputOverrideConfig(apis=apis_override_session),
            )
        ],
    )

    response_1 = await driver_config_client.get("/login")
    cookies_1 = extract_all_cookies(response_1)

    assert response_1.headers.get("anti-csrf") is not None
    assert cookies_1["sAccessToken"]["domain"] == TEST_DRIVER_CONFIG_COOKIE_DOMAIN
    assert cookies_1["sRefreshToken"]["domain"] == TEST_DRIVER_CONFIG_COOKIE_DOMAIN
    assert cookies_1["sAccessToken"]["path"] == TEST_DRIVER_CONFIG_ACCESS_TOKEN_PATH
    assert cookies_1["sRefreshToken"]["path"] == TEST_DRIVER_CONFIG_REFRESH_TOKEN_PATH
    assert cookies_1["sAccessToken"]["httponly"]
    assert cookies_1["sRefreshToken"]["httponly"]
    assert (
        cookies_1["sAccessToken"]["samesite"].lower()
        == TEST_DRIVER_CONFIG_COOKIE_SAME_SITE
    )
    assert (
        cookies_1["sRefreshToken"]["samesite"].lower()
        == TEST_DRIVER_CONFIG_COOKIE_SAME_SITE
    )

    response_3 = await driver_config_client.post(
        "/refresh",
        headers={"anti-csrf": response_1.headers.get("anti-csrf")},
        cookies={
            "sRefreshToken": cookies_1["sRefreshToken"]["value"],
        },
    )
    cookies_3 = extract_all_cookies(response_3)

    assert cookies_3["sAccessToken"]["value"] != cookies_1["sAccessToken"]["value"]
    assert cookies_3["sRefreshToken"]["value"] != cookies_1["sRefreshToken"]["value"]
    assert response_3.headers.get("anti-csrf") is not None
    assert cookies_3["sAccessToken"]["domain"] == TEST_DRIVER_CONFIG_COOKIE_DOMAIN
    assert cookies_3["sRefreshToken"]["domain"] == TEST_DRIVER_CONFIG_COOKIE_DOMAIN
    assert cookies_3["sRefreshToken"]["path"] == TEST_DRIVER_CONFIG_REFRESH_TOKEN_PATH
    assert cookies_3["sAccessToken"]["httponly"]
    assert cookies_3["sRefreshToken"]["httponly"]
    assert (
        cookies_3["sAccessToken"]["samesite"].lower()
        == TEST_DRIVER_CONFIG_COOKIE_SAME_SITE
    )
    assert (
        cookies_3["sRefreshToken"]["samesite"].lower()
        == TEST_DRIVER_CONFIG_COOKIE_SAME_SITE
    )
