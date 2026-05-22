import time, logging, math, asyncio, json
from datetime import datetime
import talib.abstract as ta
import numpy as np
import pandas as pd
from finta import TA
import freqtrade.vendor.qtpylib.indicators as qtpylib
from BinaryOptionsToolsV2.pocketoption import PocketOptionAsync as TradingClient

start = time.perf_counter()

min_payout = 85

api = TradingClient(demo)

async def get_payout(dat):
    data = dat
    full_payout = await api.payout()
    for pair in full_payout:
        if full_payout[pair] > min_payout:
            p = {}
            p['name'] = pair
            p['payout'] = full_payout[pair]
            data.append(p)
    return data

async def get_df(dat):
    data = dat
    tasks = {}
    async with asyncio.TaskGroup() as tg:
        for pair in data:
            task = tg.create_task(api.history(pair['name'], 60))
            tasks[pair['name']] = task
        await asyncio.sleep(5)
        for pair in tasks:
            try:
                res = await asyncio.shield(tasks[pair])
            except asyncio.CancelledError:
                res = None
            print(res)
    return data


async def main(data):
    dat = await get_payout(data)
    dat = await get_df(dat)
    print(dat)

if __name__ == '__main__':
    data = []
    asyncio.run(main(data))
