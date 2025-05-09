def count_up():
    i = 0
    while True:
        yield i
        i += 1

gen = count_up()
for i in gen:
    if i > 5:
        break
    print(i)
