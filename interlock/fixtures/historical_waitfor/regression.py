# CPython source excerpts under the accompanying complete LICENSE.
# https://raw.githubusercontent.com/python/cpython/a5024a261a75dafa4fb6613298dcb64a9603d9c7/Lib/test/test_asyncio/test_waitfor.py
# Dependencies are bound by the isolated observer; see manifest.json.

async def test_wait_for_issue86296(self):
    # GH-86296: The task should get cancelled and not run to completion.
    # inner completes in one cycle of the event loop so it
    # completes before the task is cancelled.

    async def inner():
        return 'done'

    inner_task = asyncio.create_task(inner())
    reached_end = False

    async def wait_for_coro():
        await asyncio.wait_for(inner_task, timeout=100)
        await asyncio.sleep(1)
        nonlocal reached_end
        reached_end = True

    task = asyncio.create_task(wait_for_coro())
    self.assertFalse(task.done())
    # Run the task
    await asyncio.sleep(0)
    task.cancel()
    with self.assertRaises(asyncio.CancelledError):
        await task
    self.assertTrue(inner_task.done())
    self.assertEqual(await inner_task, 'done')
    self.assertFalse(reached_end)
