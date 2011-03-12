# git_filter_branch_process.py
# Copyright (C) 2011 Julien Miotte <miotte.julien@gmail.com>
#
# This module is part of gfbi_core and is released under the GPLv3
# License: http://www.gnu.org/licenses/gpl-3.0.txt
#
# -*- coding: utf-8 -*-

from datetime import datetime
from subprocess import Popen, PIPE
from threading import Thread
import os
import fcntl

from git.objects.util import altz_to_utctz_str

from gfbi_core.util import Timezone

ENV_FIELDS = {'author_name'     : 'GIT_AUTHOR_NAME',
              'author_email'    : 'GIT_AUTHOR_EMAIL',
              'authored_date'   : 'GIT_AUTHOR_DATE',
              'committer_name'  : 'GIT_COMMITTER_NAME',
              'committer_email' : 'GIT_COMMITTER_EMAIL',
              'committed_date'  : 'GIT_COMMITTER_DATE' }

TEXT_FIELDS = ['message', 'summary']
ACTOR_FIELDS = ['author', 'committer']
TIME_FIELDS = ['authored_date', 'committed_date']

def run_command(command):
#    print "running %s" % command
    process = Popen(command, shell=True, stdout=PIPE)
    process.wait()

def add_assign(commit_settings, field, value):
    commit_settings += ENV_FIELDS[field] + "='%s'" % value + " "
    return commit_settings

class git_rebase_process(Thread):
    """
        Thread meant to execute and follow the progress of the git command
        process.
    """

    def __init__(self, parent, commits=[], modified={}, directory=".",
                 oldest_commit_parent=None, log=True, script=True,
                 branch="master"):
        """
            Initialization of the GitFilterBranchProcess thread.

            :param parent:
                GitModel object, parent of this thread.
            :param args:
                List of arguments that will be passed on to git filter-branch.
            :param oldest_commit_modified_parent:
                The oldest modified commit's parent.
            :param log:
                If set to True, the git filter-branch command will be logged.
            :param script:
                If set to True, the git filter-branch command will be written in
                a script that can be distributed to other developpers of the
                project.
        """
        Thread.__init__(self)

        self._oldest_parent = oldest_commit_parent

        self._log = log
        self._script = script
        self._parent = parent
        self._commits = commits
        self._modified = modified
        self._directory = directory
        self._branch = branch

        self._output = []
        self._errors = []
        self._progress = None
        self._finished = False

    def prepare_arguments(self, commit):
        commit_settings = ""
        message = ""
        for field in ("author", "committer", "authored_date", "committed_date",
                      "message"):
            if field in ACTOR_FIELDS:
                if commit in self._modified and field in self._modified[commit]:
                    name, email = self._modified[commit][field]
                else:
                    name = eval("commit." + field + ".name")
                    email = eval("commit." + field + ".email")

                if field == "author":
                    commit_settings = add_assign(commit_settings,
                                                 "author_name", name)
                    commit_settings = add_assign(commit_settings,
                                             "author_email", email)
                elif field == "committer":
                    commit_settings = add_assign(commit_settings,
                                             "committer_name", name)
                    commit_settings = add_assign(commit_settings,
                                             "committer_email", email)
            elif field == "message":
                if commit in self._modified and field in self._modified[commit]:
                    message = self._modified[commit][field]
                else:
                    message = commit.message

                message = message.replace('\\', '\\\\')
                message = message.replace('$', '\\\$')
                # Backslash overflow !
                message = message.replace('"', '\\\\\\"')
                message = message.replace("'", "'\"\\\\\\'\"'")
                message = message.replace('(', '\(')
                message = message.replace(')', '\)')
            elif field in TIME_FIELDS:
                if commit in self._modified and field in self._modified[commit]:
                    _timestamp = self._modified[commit][field]
                else:
                    _timestamp = eval("commit." + field)
                _utc_offset = altz_to_utctz_str(commit.author_tz_offset)
                _tz = Timezone(_utc_offset)
                _dt = datetime.fromtimestamp(_timestamp).replace(tzinfo=_tz)
                value = _dt.strftime("%a %b %d %H:%M:%S %Y %Z")
                commit_settings = add_assign(commit_settings, field, value)

        return commit_settings, message

    def run(self):
        """
            Main method of the script. Launches the git command and
            logs/generate scripts if the options are set.
        """
        os.chdir(self._directory)
        run_command('git checkout %s -b tmp_rebase' % self._oldest_parent.hexsha)
        oldest_index = self._commits.index(self._oldest_parent)
        for commit in reversed(self._commits[:oldest_index]):
            FIELDS, MESSAGE = self.prepare_arguments(commit)
            run_command('git cherry-pick -n %s' % commit.hexsha)
            run_command(FIELDS + ' git commit -m "%s"' % MESSAGE)
        run_command('git branch -M %s' % self._branch)
        self._finished = True

    def progress(self):
        """
            Returns the progress percentage
        """
        return self._progress

    def output(self):
        """
            Returns the output as a list of lines
        """
        return list(self._output)

    def errors(self):
        """
            Returns the errors as a list of lines
        """
        return list(self._errors)

    def is_finished(self):
        """
            Returns self._finished
        """
        return self._finished
