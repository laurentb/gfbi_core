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

from git.objects.util import altz_to_utctz_str

from gfbi_core.util import Timezone, Index
from gfbi_core import ENV_FIELDS, TEXT_FIELDS, ACTOR_FIELDS, TIME_FIELDS

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

    def __init__(self, parent, commits=list(), modifications=dict(),
                 directory=".", oldest_commit_parent=None, log=True,
                 oldest_commit_parent_row=0,
                 script=True, branch="master"):
        """
            Initialization of the GitFilterBranchProcess thread.

            :param parent:
                GitModel object, parent of this thread.
            :param args:
                List of arguments that will be passed on to git filter-branch.
            :param oldest_commit_parent:
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
        self._oldest_parent_row = oldest_commit_parent_row

        self._log = log
        self._script = script
        self._model = parent
        self._commits = commits
        self._modifications = modifications
        self._directory = directory
        self._branch = branch

        self._output = []
        self._errors = []
        self._progress = None
        self._finished = False

    def prepare_arguments(self, row):
        commit_settings = ""
        message = ""

        for field in ACTOR_FIELDS:
            index = Index(row=row, column=self._model.get_columns().index(field))
            value = self._model.data(index)
            commit_settings = add_assign(commit_settings, field, value)

        for field in TIME_FIELDS:
            index = Index(row=row, column=self._model.get_columns().index(field))
            _timestamp, _tz = self._model.data(index)
            _dt = datetime.fromtimestamp(_timestamp).replace(tzinfo=_tz)
            value = _dt.strftime("%a %b %d %H:%M:%S %Y %Z")
            commit_settings = add_assign(commit_settings, field, value)

        field = "message"
        index = Index(row=row, column=self._model.get_columns().index(field))
        message = self._model.data(index)

        message = message.replace('\\', '\\\\')
        message = message.replace('$', '\\\$')
        # Backslash overflow !
        message = message.replace('"', '\\\\\\"')
        message = message.replace("'", "'\"\\\\\\'\"'")
        message = message.replace('(', '\(')
        message = message.replace(')', '\)')

        return commit_settings, message

    def run(self):
        """
            Main method of the script. Launches the git command and
            logs/generate scripts if the options are set.
        """
        os.chdir(self._directory)
        run_command('git checkout %s -b tmp_rebase' %
                    self._oldest_parent.hexsha)
        oldest_index = self._oldest_parent_row
        for row in xrange(oldest_index - 1, -1, -1):
            hexsha = self._model.data(Index(row=row, column=0))
            FIELDS, MESSAGE = self.prepare_arguments(row)

            run_command('git cherry-pick -n %s' % hexsha)
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