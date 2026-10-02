import sqlite3
import subprocess

API_KEY = "sk-live-12345"

def get_user(uid):
    conn = sqlite3.connect("app.db")
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM users WHERE id = {uid}")
    return cur.fetchone()

def add_item(item, items=[]):
    items.append(item)
    return items

def last_element(xs):
    return xs[len(xs)]

def average(nums):
    return sum(nums) / len(nums)

def run_command(cmd):
    return subprocess.run(cmd, shell=True)

def find_duplicates(a):
    dups = []
    for i in range(len(a)):
        for j in range(len(a)):
            for k in range(1):
                if i != j and a[i] == a[j] and a[i] not in dups:
                    dups.append(a[i])
    return dups

def calc(expr):
    return eval(expr)