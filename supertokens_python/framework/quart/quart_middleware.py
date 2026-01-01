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
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Optional, Union

from supertokens_python.framework import BaseResponse

if TYPE_CHECKING:
    from quart import Quart


class Middleware:
    def __init__(self, app: Quart):
        self.app = app
        self.set_before_after_request()
        self.set_error_handler()

    def set_before_after_request(self):
        app = self.app
        from quart.wrappers import Response

        from supertokens_python.framework.quart.quart_request import QuartRequest
        from supertokens_python.framework.quart.quart_response import QuartResponse
        from supertokens_python.supertokens import manage_session_post_response
        from supertokens_python.utils import default_user_context

        # There is an error in the typing provided by quart, so we ignore it
        # for now.
        @app.before_request  # type: ignore
        async def _():
            from quart import request
            from quart.wrappers import Response

            from supertokens_python import Supertokens

            st = Supertokens.get_instance()

            request_ = QuartRequest(request)
            response_ = QuartResponse(Response())
            user_context = default_user_context(request_)

            result: Union[BaseResponse, None] = await st.middleware(
                request_, response_, user_context
            )

            if result is not None:
                if isinstance(result, QuartResponse):
                    return result.response
                raise Exception("Should never come here")
            return None

        @app.after_request
        async def _(response: Response):
            from quart import g

            response_ = QuartResponse(response)
            if hasattr(g, "supertokens") and g.supertokens is not None:
                manage_session_post_response(g.supertokens, response_, {})

            return response_.response

        @app.teardown_request
        async def _(_):
            from quart import g

            if hasattr(g, "supertokens"):
                # this is to ensure there are no shared objects between requests.
                # calling any other API with a shared request causes a security issue, resulting in unintentional
                # sign-ins. More on this here - https://github.com/supertokens/supertokens-python/issues/463
                g.pop("supertokens")

    def set_error_handler(self):
        app = self.app
        from quart import request

        from supertokens_python.exceptions import SuperTokensError

        @app.errorhandler(SuperTokensError)
        async def _(error: Exception):
            from quart.wrappers import Response

            from supertokens_python import Supertokens
            from supertokens_python.framework.quart.quart_request import QuartRequest
            from supertokens_python.framework.quart.quart_response import QuartResponse
            from supertokens_python.utils import default_user_context

            st = Supertokens.get_instance()
            response = Response(json.dumps({}), mimetype="application/json", status=200)
            base_request = QuartRequest(request)
            user_context = default_user_context(base_request)

            result: Optional[BaseResponse] = await st.handle_supertokens_error(
                base_request,
                error,
                QuartResponse(response),
                user_context,
            )
            if result is not None:
                if not isinstance(result, QuartResponse):
                    raise Exception("should never happen")

                return result.response
            raise Exception("Should never come here")
