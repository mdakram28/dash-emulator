import asyncio
from types import SimpleNamespace

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
    context.args.quic_client = QuicClientImpl()


@when("The client is asked to get content from an URL")
def step_impl(context):
    """
    Parameters
    ----------
    context : behave.runner.Context
    """
    # context.args.url = "https://lab.yangliu.xyz/videos/BBB/output.mpd"
    context.args.url = "https://oracle1.jace.website/videos/BBB/output.mpd"


@then("The client get it")
def step_impl(context):
    """
    Parameters
    ----------
    context : behave.runner.Context
    """
    quic_client: QuicClientImpl = context.args.quic_client
    # asyncio.run(quic_client.get(context.args.url))

    asyncio.run(quic_client.download(context.args.url))
