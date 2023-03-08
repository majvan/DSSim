import time

class Thing:
    async def __aenter__(self):
        retval = await delay()
        return self
    
    async def __aexit__(self, *args):
        print("Exiting a thing")

    async def __await__(self):
        yield True
        return

class Delay:
	def __await__(self):
		print("Delays, delays...")
		return 'abc'

async def delay():
    print("Delays, delays...")
    # yield from iter([1, 2])  # This won't work
    return 'cde'

async def coro():
	print("Hi, I'm a coroutine")
	# await Delay()
	async with Thing() as obj:
		print("I have", obj)
	print("The context manager is all done now.")
	# await Delay()
	print("Bye!")

waitfor = coro()
while True:
    try:
        waitfor.send(None)
    except StopIteration:
        break
    time.sleep(2)