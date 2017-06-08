import os
import pstats
import cProfile
import marshal
import json
import tempfile
from StringIO import StringIO
from Products.Five.browser import BrowserView

from plone import api


def jsonify(request, data, cache=False):
    header = request.RESPONSE.setHeader
    header("Content-Type", "application/json")
    if cache:
        header("Expires", "Sun, 17-Jan-2038 19:14:07 GMT")
    return json.dumps(data, indent=2, sort_keys=True)


def set_headers(request, name=''):
    content_disp = 'attachment; filename={0}.profile'.format(name)
    request.response.setHeader('Content-Type', 'application/octet-steam')
    request.response.setHeader('Content-Disposition', content_disp)


def prepare_download(profile):
    profile.create_stats()
    dump = marshal.dumps(profile.stats)

    stream = StringIO()
    stream.write(dump)

    stream.seek(0)

    return stream


def download(request, profile, name):
    stream = prepare_download(profile)
    set_headers(request, name)
    return stream.read()


def profile_context(context, **kwargs):
    profiler = cProfile.Profile()
    profiler.runcall(context, **kwargs)
    return profiler


class ProfileView(BrowserView):

    def run_profile(self, target=None, **kwargs):
        if 'target' in self.request:
            target = self.request.get('target')

        if 'kwargs' in self.request:
            kwargs = json.loads(self.request.get('kwargs', '{}'))

        target_context = (
            getattr(self.context, target, None)
            if target is not None
            else self.context
        )

        return (
            profile_context(target_context, **kwargs),
            target_context.__name__
        )

    def main(self):
        profile, target = self.run_profile()
        return download(self.request, profile, name=target)

    def make_temp(self):
        profile, name = self.run_profile()
        handle, path = tempfile.mkstemp('.profile', name + '_')
        profile.dump_stats(path)
        os.close(handle)
        return path

    def query_stats(self, stats, line):
        command = [x.strip() for x in line.strip().split(' ')]
        cmd, qargs = command[0], command[1:]
        qargs = [int(arg) if arg.isdigit() else arg for arg in qargs]

        if cmd == 'sort':
            stats.sort_stats(*qargs)
        elif cmd == 'reverse':
            stats.reverse_order()
        elif cmd == 'strip':
            stats.strip_dirs()
        elif cmd in ['callers', 'callees', 'stats']:
            return cmd, qargs

    def ajax(self):
        path = self.request.get('path', '')
        query = json.loads(self.request.get('query', '[]'))

        if not path:
            path = self.make_temp()

        stats_out = StringIO()
        stats = pstats.Stats(path, stream=stats_out)

        query_result = None
        for line in query:
            query_result = self.query_stats(stats, line)
            if query_result:
                break

        if query_result is None:
            query_result = ('stats', '')

        qcmd, qargs = query_result
        if qcmd == 'callers':
            stats.print_callers(*qargs)
        elif qcmd == 'callees':
            stats.print_callees(*qargs)
        elif qcmd == 'stats':
            stats.print_stats(*qargs)

        stats_out.seek(0)

        result = {
            'profile': path,
            'data': stats_out.read()
        }

        return jsonify(self.request, result)

    @property
    def site_url(self):
        return api.portal.get().absolute_url()

    @property
    def context_name(self):
        try:
            return self.request.get('target',  self.context.__name__)
        except:
            return 'Unknown context'
