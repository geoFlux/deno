#!/usr/bin/env python
# Copyright 2018-2020 the Deno authors. All rights reserved. MIT license.
# Many tests expect there to be an http server on port 4545 servering the deno
# root directory.
from collections import namedtuple
from contextlib import contextmanager
import os
import SimpleHTTPServer
import SocketServer
import socket
import sys
from time import sleep
from threading import Thread
from util import root_path
import ssl
import getopt

PORT = 4545
REDIRECT_PORT = 4546
ANOTHER_REDIRECT_PORT = 4547
DOUBLE_REDIRECTS_PORT = 4548
INF_REDIRECTS_PORT = 4549

QUIET = '-v' not in sys.argv and '--verbose' not in sys.argv
USE_HTTPS = '--use-https' in sys.argv
PROTOCOL = 'https:' if USE_HTTPS else 'http:'

CERT_FILE = ""
KEY_FILE = ""
try:
    unixOptions = "v"
    gnuOptions = ["verbose", "use-https", "certfile=", "keyfile="]
    arguments, values = getopt.getopt(sys.argv[1:], unixOptions, gnuOptions)

    for currentArgument, currentValue in arguments:
        if currentArgument in ("--certfile"):
            CERT_FILE = currentValue
        if currentArgument in ("--keyfile"):
            KEY_FILE = currentValue

except getopt.error as err:
    print(str(err))
    sys.exit(2)


class SSLTCPServer(SocketServer.TCPServer):
    def __init__(self,
                 server_address,
                 request_handler,
                 certfile,
                 keyfile,
                 ssl_version=ssl.PROTOCOL_TLSv1_2,
                 bind_and_activate=True):
        SocketServer.TCPServer.__init__(self, server_address, request_handler,
                                        bind_and_activate)
        self.certfile = certfile
        self.keyfile = keyfile
        self.ssl_version = ssl_version

    def get_request(self):
        newsocket, fromaddr = self.socket.accept()
        connstream = ssl.wrap_socket(newsocket,
                                     server_side=True,
                                     certfile=self.certfile,
                                     keyfile=self.keyfile,
                                     ssl_version=self.ssl_version)
        return connstream, fromaddr


class SSLThreadingTCPServer(SocketServer.ThreadingMixIn, SSLTCPServer):
    pass


class QuietSimpleHTTPRequestHandler(SimpleHTTPServer.SimpleHTTPRequestHandler):
    def log_request(self, code='-', size='-'):
        if not QUIET:
            SimpleHTTPServer.SimpleHTTPRequestHandler.log_request(
                self, code, size)


class ContentTypeHandler(QuietSimpleHTTPRequestHandler):
    def do_GET(self):

        # Check if there is a custom header configuration ending
        # with ".header" before sending the file
        maybe_header_file_path = "./" + self.path + ".header"
        if os.path.exists(maybe_header_file_path):
            self.protocol_version = 'HTTP/1.1'
            self.send_response(200, 'OK')

            f = open(maybe_header_file_path)
            for line in f:
                kv = line.split(": ")
                self.send_header(kv[0].strip(), kv[1].strip())
            f.close()
            self.end_headers()

            body = open("./" + self.path)
            self.wfile.write(body.read())
            body.close()
            return

        if "etag_script.ts" in self.path:
            self.protocol_version = 'HTTP/1.1'
            if_not_match = self.headers.getheader('if-none-match')
            if if_not_match == "33a64df551425fcc55e":
                self.send_response(304, 'Not Modified')
                self.send_header('Content-type', 'application/typescript')
                self.send_header('ETag', '33a64df551425fcc55e')
                self.end_headers()
            else:
                self.send_response(200, 'OK')
                self.send_header('Content-type', 'application/typescript')
                self.send_header('ETag', '33a64df551425fcc55e')
                self.end_headers()
                self.wfile.write(bytes("console.log('etag')"))
            return

        if "xTypeScriptTypes.js" in self.path:
            self.protocol_version = "HTTP/1.1"
            self.send_response(200, 'OK')
            self.send_header('Content-type', 'application/javascript')
            self.send_header('X-TypeScript-Types', './xTypeScriptTypes.d.ts')
            self.end_headers()
            self.wfile.write(bytes("export const foo = 'foo';"))
            return

        if "xTypeScriptTypes.d.ts" in self.path:
            self.protocol_version = "HTTP/1.1"
            self.send_response(200, 'OK')
            self.send_header('Content-type', 'application/typescript')
            self.end_headers()
            self.wfile.write(bytes("export const foo: 'foo';"))
            return

        if "referenceTypes.js" in self.path:
            self.protocol_version = "HTTP/1.1"
            self.send_response(200, 'OK')
            self.send_header('Content-type', 'application/javascript')
            self.end_headers()
            self.wfile.write(
                bytes('/// <reference types="./xTypeScriptTypes.d.ts" />\r\n'
                      'export const foo = "foo";\r\n'))
            return

        if "multipart_form_data.txt" in self.path:
            self.protocol_version = 'HTTP/1.1'
            self.send_response(200, 'OK')
            self.send_header('Content-type',
                             'multipart/form-data;boundary=boundary')
            self.end_headers()
            self.wfile.write(
                bytes('Preamble\r\n'
                      '--boundary\t \r\n'
                      'Content-Disposition: form-data; name="field_1"\r\n'
                      '\r\n'
                      'value_1 \r\n'
                      '\r\n--boundary\r\n'
                      'Content-Disposition: form-data; name="field_2"; '
                      'filename="file.js"\r\n'
                      'Content-Type: text/javascript\r\n'
                      '\r\n'
                      'console.log("Hi")'
                      '\r\n--boundary--\r\n'
                      'Epilogue'))
            return
        return SimpleHTTPServer.SimpleHTTPRequestHandler.do_GET(self)

    def do_POST(self):
        # Simple echo server for request reflection
        if "echo_server" in self.path:
            self.protocol_version = 'HTTP/1.1'
            self.send_response(200, 'OK')
            if self.headers.has_key('content-type'):
                self.send_header('content-type',
                                 self.headers.getheader('content-type'))
            if self.headers.has_key('user-agent'):
                self.send_header('user-agent',
                                 self.headers.getheader('user-agent'))
            self.end_headers()
            data_string = self.rfile.read(int(self.headers['Content-Length']))
            self.wfile.write(bytes(data_string))
            return
        self.protocol_version = 'HTTP/1.1'
        self.send_response(501)
        self.send_header('content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(bytes('Server does not support this operation'))

    def guess_type(self, path):
        if ".t1." in path:
            return "text/typescript"
        if ".t2." in path:
            return "video/vnd.dlna.mpeg-tts"
        if ".t3." in path:
            return "video/mp2t"
        if ".t4." in path:
            return "application/x-typescript"
        if ".j1." in path:
            return "text/javascript"
        if ".j2." in path:
            return "application/ecmascript"
        if ".j3." in path:
            return "text/ecmascript"
        if ".j4." in path:
            return "application/x-javascript"
        if "form_urlencoded" in path:
            return "application/x-www-form-urlencoded"
        if "no_ext" in path:
            return "text/typescript"
        if "unknown_ext" in path:
            return "text/typescript"
        if "mismatch_ext" in path:
            return "text/javascript"
        return SimpleHTTPServer.SimpleHTTPRequestHandler.guess_type(self, path)


RunningServer = namedtuple("RunningServer", ["server", "thread"])


def get_socket(port, handler):
    SocketServer.TCPServer.allow_reuse_address = True
    if os.name != "nt":
        # We use AF_INET6 to avoid flaky test issue, particularly with
        # the test 019_media_types. It's not well understood why this fixes the
        # flaky tests, but it does appear to...
        # See https://github.com/denoland/deno/issues/3332
        SocketServer.TCPServer.address_family = socket.AF_INET6

    if USE_HTTPS:
        return SSLThreadingTCPServer(("", port), handler, CERT_FILE, KEY_FILE)
    return SocketServer.TCPServer(("", port), handler)


def server():
    os.chdir(root_path)  # Hopefully the main thread doesn't also chdir.
    Handler = ContentTypeHandler
    Handler.extensions_map.update({
        ".ts": "application/typescript",
        ".js": "application/javascript",
        ".tsx": "application/typescript",
        ".jsx": "application/javascript",
        ".json": "application/json",
    })
    s = get_socket(PORT, Handler)
    if not QUIET:
        print "Deno test server %s//localhost:%d/" % (PROTOCOL, PORT)
    return RunningServer(s, start(s))


def base_redirect_server(host_port, target_port, extra_path_segment=""):
    os.chdir(root_path)
    target_host = "%s//localhost:%d" % (PROTOCOL, target_port)

    class RedirectHandler(QuietSimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(301)
            self.send_header('Location',
                             target_host + extra_path_segment + self.path)
            self.end_headers()

    s = get_socket(host_port, RedirectHandler)
    if not QUIET:
        print "redirect server %s//localhost:%d/ -> %s//localhost:%d/" % (
            PROTOCOL, host_port, PROTOCOL, target_port)
    return RunningServer(s, start(s))


# redirect server
def redirect_server():
    return base_redirect_server(REDIRECT_PORT, PORT)


# another redirect server pointing to the same port as the one above
# BUT with an extra subdir path
def another_redirect_server():
    return base_redirect_server(ANOTHER_REDIRECT_PORT,
                                PORT,
                                extra_path_segment="/cli/tests/subdir")


# redirect server that points to another redirect server
def double_redirects_server():
    return base_redirect_server(DOUBLE_REDIRECTS_PORT, REDIRECT_PORT)


# redirect server that points to itself
def inf_redirects_server():
    return base_redirect_server(INF_REDIRECTS_PORT, INF_REDIRECTS_PORT)


def start(s):
    thread = Thread(target=s.serve_forever, kwargs={"poll_interval": 0.05})
    thread.daemon = True
    thread.start()
    return thread


@contextmanager
def spawn():
    servers = (server(), redirect_server(), another_redirect_server(),
               double_redirects_server())
    while any(not s.thread.is_alive() for s in servers):
        sleep(0.01)
    try:
        print "ready"
        yield servers
    finally:
        for s in servers:
            s.server.shutdown()


def main():
    with spawn() as servers:
        try:
            while all(s.thread.is_alive() for s in servers):
                sleep(1)
        except KeyboardInterrupt:
            pass
    sys.exit(1)


if __name__ == '__main__':
    main()
