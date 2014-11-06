#!/usr/bin/env python

import os
import sys
import stat
import errno
import logging
import StringIO

try:
    import _find_fuse_parts
except ImportError:
    pass
import fuse

from linode import Api

fuse.fuse_python_api = (0, 2)

write_cache = {}

class LinodeFSStat(fuse.Stat):

    def __init__(self):
        self.st_mode = 0
        self.st_ino = 0
        self.st_dev = 0
        self.st_nlink = 0
        self.st_uid = 0
        self.st_gid = 0
        self.st_size = 0
        self.st_atime = 0
        self.st_mtime = 0
        self.st_ctime = 0

class LinodeFS(fuse.Fuse):
    _api = None
    _objects_to_create = []

    def __init__(self, *args, **kwargs):
        fuse.Fuse.__init__(self, *args, **kwargs)

        logging.basicConfig(filename='linodefs.log', level=logging.DEBUG)
        logging.debug("Starting LinodeFS")

    def make_connection(self):
        if hasattr(self, 'api_url'):
            API.endpoint = self.api_url

        self._api = Api(self.api_key)

    @property
    def api_handle(self):
        if not self._api:
            self.make_connection

        return self._api

    def _read_linode_names(self):
        return [container.name for container in
                self.api_handle.list_containers()]

    def _get_object(self, path_tokens):
        """Return an object instance from path_tokens (i.e. result
        of path.split('/') or None if object doesn't exist"""
        container_name, object_name = path_tokens[1], path_tokens[2]
        try:
            container = self.api_handle.get_container(container_name)
            return container.get_object(object_name)
        except (ContainerDoesNotExistError, ObjectDoesNotExistError):
            return None

    def getattr(self, path):
        logging.debug("getattr(path='%s')" % path)

        st = CloudStat()

        if path == '/':
            st.st_mode = stat.S_IFDIR | 0755
            st.st_nlink = 2
            return st
        elif path in self._objects_to_create:
            logging.debug("getattr(path='%s'): file is scheduled for creation" % (path))
            st.st_mode = stat.S_IFREG | 0644
            st.st_nlink = 1
            st.st_size = 0
            return st

        path_tokens = path.split('/')

        if 2 == len(path_tokens):
            linode_names = self._read_linode_names()

            if path_tokens[1] in linode_names:
                st.st_mode = stat.S_IFDIR | 0755
                st.st_nlink = 2
                return st
            else:
                return -errno.ENOENT
        elif 3 == len(path_tokens):
            obj = self._get_object(path_tokens)

            if obj:
                st.st_mode = stat.S_IFREG | 0444
                st.st_nlink = 1
                st.st_size = obj.size
            else:
                # getattr() might be called for a new file which doesn't
                # exist yet, so we need to make it writable in such case
                #st.st_mode = stat.S_IFREG | 0644
                #st.st_nlink = 1
                #st.st_size = 0
                return -errno.ENOENT
            return st

        return -errno.ENOENT

    def readdir(self, path, offset):
        logging.debug("readdir(path='%s', offset='%s')" % (path, offset))

        if "/" == path:
            try:
                linode_names = [linode['LABEL'] for linode in
                    self.api_handle.linode.list()]

                logging.debug("linode names = %s" % linode_names)
                dirs = [".", ".."] + linode_names

                logging.debug("dirs = %s" % dirs)

                for r in  dirs:
                    logging.debug("yielding %s" % r)
                    yield fuse.Direntry(r)
                #return dirs
            except Exception:
                logging.exception("exception in readdir()")
        else:
            path_tokens = path.split("/")

            if 2 != len(path_tokens):
                # we should only have 1 level depth
                logging.warning("Path '%s' is deeper than it should" % path)
                return

            try:
                linode_id = path_tokens[1]
                linode = self.api_handle.linode.list({linodeid:linode_id})
                dirs = [".", "..","info"] +  [str('disk'+obj.diskid) for disk in
                        self.api_handle.linode.disk.list({linodeid:linode_id})]

                logging.debug("dirs = %s" % dirs)

                for r in dirs:
                    yield fuse.Direntry(r)
            except Exception:
                logging.exception("exception while trying to list container objects")

    def mkdir(self, path, mode):
        logging.debug("mkdir(path='%s', mode='%s')" % (path, mode))

        path_tokens = path.split('/')
        if 2 != len(path_tokens):
            logging.warning("attempting to create a non-container dir %s" % path)
            return -errno.EOPNOTSUPP

        container_name = path_tokens[1]

        self.api_handle.create_container(container_name)

        return 0

    def rmdir(self, path):
        logging.debug("rmdir(path='%s')" % (path,))

        path_tokens = path.split('/')

        if 1 == len(path_tokens):
            return -errno.EPERM
        elif 2 == len(path_tokens):
            container_name = path_tokens[1]

            try:
                container = self.api_handle.get_container(container_name)
            except ContainerDoesNotExistError:
                return -errno.ENOENT

            if 0 != len(container.list_objects()):
                return -errno.ENOTEMPTY

            container.delete()

            return 0
        elif 3 <= len(path_tokens):
            return -errno.EOPNOTSUPP

    def mknod(self, path, mode, dev):
        logging.debug("mknod(path='%s', mode='%s', dev='%s')" % (path, mode, dev))

        try:
            path_tokens = path.split('/')
            if 3 != len(path_tokens):
                return -errno.EPERM

            container_name = path_tokens[1]
            object_name = path_tokens[2]

            self.api_handle.upload_object_via_stream(StringIO.StringIO('\n'),
                    self.api_handle.get_container(container_name),
                    object_name,
                    extra={"content_type": "application/octet-stream"})
            return 0
        except Exception:
            logging.exception("exception in mknod()")

    def open(self, path, flags):
        logging.debug("open(path='%s', flags='%s')" % (path, flags))
        return 0
        path_tokens = path.split('/')

        if 3 != len(path_tokens):
            logging.warning("path_tokens != 3")
            return -errno.EOPNOTSUPP

        try:
#            obj = self._get_object(path_tokens)
#            # we allow opening existing files in read-only mode
#            if obj:
#                accmode = os.O_RDONLY | os.O_WRONLY | os.O_RDWR
#                if (flags & accmode) != os.O_RDONLY:
#                    return -errno.EACCES
            return 0
        except Exception:
            logging.exception("exception in open()")

    def read(self, path, size, offset):
        logging.debug("read(path='%s', size=%s, offset=%s)" % (path, size, offset))

        path_tokens = path.split('/')
        if 3 != len(path_tokens):
            return -errno.EOPNOTSUPP

        container_name, object_name = path_tokens[1], path_tokens[2]
        try:
            container = self.api_handle.get_container(container_name)
            obj = container.get_object(object_name)
        except (ContainerDoesNotExistError, ObjectDoesNotExistError):
            return -errno.ENOENT

        try:
            content = ''.join([line for line in obj.as_stream()])
        except:
            logging.exception("error reading file content")
            return

        slen = len(content)
        if offset < slen:
            if offset + size > slen:
                size = slen - offset
            response = content[offset:offset+size]
        else:
            response = ''
        return response

    def write(self, path, buff, offset):
        logging.debug("write(path='%s', buff=<skip>, offset='%s')" % (path, offset))

        try:
            if path not in write_cache:
                write_cache[path] = [buff,]
            else:
                write_cache.append(buff)

            return len(buff)
        except Exception:
            logging.exception("exception in write()")

    def unlink(self, path):
        logging.debug("unlink(path='%s')" % (path,))

        try:
            path_tokens = path.split('/')
            if 3 != len(path_tokens):
                return

            obj = self._get_object(path_tokens)
            if not obj:
                return -errno.ENOENT

            obj.delete()
            return 0
        except Exception:
            logging.exception("error while processing unlink()")

    def release(self, path, flags):
        logging.debug("release(path='%s', flags='%s')" % (path, flags))

        # XXX: what's the nature of this?
        if "-" == path:
            return 0

        try:
            path_tokens = path.split("/")
            container_name, object_name = path_tokens[1], path_tokens[2]

            if len(write_cache[path]) > 0:
                self.unlink(path)
                self.api_handle.upload_object_via_stream(StringIO.StringIO(''.join(write_cache[path])),
                        self.api_handle.get_container(container_name),
                        object_name,
                        extra={"content_type": "application/octet-stream"})
                del write_cache[path]
            return 0
        except KeyError:
            logging.warning("no cached entry for path: %s" % path)
            return 0
        except Exception:
            logging.exception("exception in release()")

    def truncate(self, path, size):
        return 0

    def utime(self, path, times):
        return 0

    def fsync(self, path, isfsyncfile):
        return 0

def main():
    usage="""
LinodeFS

""" + fuse.Fuse.fusage
    server = LinodeFS(version="%prog " + fuse.__version__,
                     usage=usage,
                     dash_s_do='setsingle')

    server.parser.add_option(mountopt='api_key', metavar='API_KEY',
            help=("API Key"))
    server.parser.add_option(mountopt='api_url', metavar='API_URL',
            help=("API URL"))
    server.parse(values=server, errex=1)

    if not (hasattr(server, 'api_key')):
        print >>sys.stderr, "Please specify an API Key."
        sys.exit(1)

    try:
        server.make_connection()
    except Exception, err:
        print >>sys.stderr, "Cannot connect to Linode API: %s" % str(err)
        sys.exit(1)

    server.main()

if __name__ == '__main__':
    main()
