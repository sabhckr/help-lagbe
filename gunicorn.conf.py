import multiprocessing
import os

bind = os.environ.get("BIND", "127.0.0.1:8000")
workers = int(os.environ.get("WEB_CONCURRENCY", max(2, multiprocessing.cpu_count())))
threads = 2
timeout = 60
accesslog = "-"
access_log_format = '%(h)s %(l)s %(t)s "%(m)s %(U)s" %(s)s %(b)s %(L)s'  # no query strings, no referrer, no UA
errorlog = "-"
forwarded_allow_ips = os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1")
limit_request_line = 4094
limit_request_field_size = 8190
