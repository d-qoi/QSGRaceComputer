from random import randint

def maybe_get_data():
    if randint(0, 1) == 1:
        return "data"
    raise Exception()

def test():
    try:
        data = maybe_get_data()
    except Exception as e:
        data = ''
        pass
    print(data)
