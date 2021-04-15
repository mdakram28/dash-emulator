import asyncio
from types import SimpleNamespace

import logging
from behave import *

from dash_emulator_quic.quic.client import QuicClientImpl

use_step_matcher("re")


@given("A QUIC Client")
def step_impl(context):
    """
    Parameters
    ----------
    context : behave.runner.Context
    """
    context.args = SimpleNamespace()
    context.args.quic_client = QuicClientImpl([])


@when("The client is asked to get content from an URL")
def step_impl(context):
    """
    Parameters
    ----------
    context : behave.runner.Context
    """
    # context.args.url = "https://lab.yangliu.xyz/videos/BBB/output.mpd"
    context.args.url1 = "https://oracle1.jace.website/videos/BBB/chunk-stream0-00010.m4s"
    context.args.url2 = "https://oracle1.jace.website/videos/BBB/chunk-stream0-00011.m4s"


@then("The client get it")
def step_impl(context):
    """
    Parameters
    ----------
    context : behave.runner.Context
    """
    logging.basicConfig(level=logging.DEBUG)
    quic_client: QuicClientImpl = context.args.quic_client
    # asyncio.run(quic_client.get(context.args.url))

    async def foo():
        await quic_client.download(context.args.url1)
        await quic_client.download(context.args.url2)
    asyncio.run(foo())
