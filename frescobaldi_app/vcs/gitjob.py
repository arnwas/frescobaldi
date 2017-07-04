# This file is part of the Frescobaldi project, http://www.frescobaldi.org/
#
# Copyright (c) 2008 - 2014 by Wilbert Berendsen
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
# See http://www.gnu.org/licenses/ for more information.

"""
Execute a single Git command, either blocking or non-blocking.
The output of the command will be stored in the _stdout and _stderr fields,
run_blocking() will return the data while run() will invoke the finished signal,
giving the caller the opportunity to retrieve the data.
"""

import re
import time

from PyQt5.QtCore import QObject, QProcess, pyqtSignal


class Git(QObject):

    # "custom" signals for passing on QProcess's signals
    finished = pyqtSignal(QObject)
    readyReadStandardError = pyqtSignal()
    readyReadStandardOutput = pyqtSignal()
    started = pyqtSignal()
    stateChanged = pyqtSignal(QProcess.ProcessState)
    errorOccurred = pyqtSignal(QProcess.ProcessError)
    
    # emits when the receiver finish executing
    executed = pyqtSignal(int)

    def __init__(self, owner):
        super().__init__()
        # TODO: check for preference
        executable = 'git'
        # args could be set in advance
        self.preset_args = None 
        self._version = None
        self._isbinary = False
        self._stderr = None
        self._stdout = None

        # Create and configure QProcess object
        self._process = process = QProcess()
        process.setProgram(executable)
        process.setWorkingDirectory(owner._root_path) # TODO: change to a .root() method in gitrepo.Repo()

        # Connect QProcess's signals to our own intermediate slots or our own signals
        process.finished.connect(self._finished)
        process.readyReadStandardError.connect(self.readyReadStandardError)
        process.readyReadStandardOutput.connect(self.readyReadStandardOutput)
        process.started.connect(self.started)
        process.stateChanged.connect(self.stateChanged)
        try:
            process.errorOccurred.connect(self.errorOccurred)
        except AttributeError:
            # errorOccurred may not be supported 
            process.error.connect(self.errorOccurred)  

    def _start_process(self, args, isbinary=False):
        """
        Internal command preparing and starting the Git process
        """
        if args == None:
            raise Exception("Command 'args' is not specified")
        self._stderr = None
        self._stdout = None
        self._isbinary = isbinary
        self._process.setArguments(args)
        self._process.start()

    def run(self, args = None, isbinary=False):
        """
        Asynchronously run the command.
        
        Arguments:
                  args([]): arguments of the Git command. 
                            If 'args' is not given, 'preset_args' will be used.
            isbinary(bool): True - return the binary result.
                            False - return the 'utf-8' encoded string list.

        Results will only be available after the _finished() slot has been executed
        """
        args = self.preset_args if args == None else args   
        self._start_process(args, isbinary)

    def run_blocking(self, args = None, isbinary = False):
        """
        Synchronously run the command.

        Arguments:
                  args([]): arguments of the Git command. 
                            If 'args' is not given, 'preset_args' will be used.
            isbinary(bool): True - return the binary result.
                            False - return the 'utf-8' encoded string list.

        Results will be returned but are also available through stdout() and stderr() afterwards
        """
        args = self.preset_args if args == None else args
        self._start_process(args, isbinary)
        self._process.waitForFinished()
        return (self._stdout, self._stderr)

    def isRunning(self):
        """
        Returns True if the process is currently running.
        """
        return not self._process.state() == QProcess.NotRunning

    def kill(self):
        """
        Kills the process if it is running
        """
        if self.isRunning():
            # Note: Qt handles the OS differences transparently
            self._process.kill()

    def _tic(self):
        """
        Helper function to count how much time a git command takes
        """
        self._timer = time.perf_counter()

    def _toc(self, args = []):
        """
        Helper function to count how much time a git command takes
        """
        if self._timer:
            print('command git {} takes {}'.format(' '.join(args), 
                time.perf_counter()-self._timer))
            self._timer = None

    def _handle_results(self):
        """
        will be called when the process has completed.
        Populates the result fields
        """
        if self._isbinary:
            self._stderr = self._process.readAllStandardError()
            self._stdout = self._process.readAllStandardOutput()
        else:
            self._stdout = str(self._process.readAllStandardOutput(), 'utf-8').split('\n')
            if not self._stdout[-1]:
                self._stdout.pop()
            self._stderr = str(self._process.readAllStandardError(), 'utf-8').split('\n')
            if not self._stderr[-1]:
                self._stderr.pop()

    def _finished(self, exitcode, exitstatus):
        """
        Called when the process has completed.
        process results and forward the signal
        
        exitcode == 0 : Process executes successfully. 
                        Result will output to stdout().
        exitcode == 1 : Process returns an error message.
                        Error message will output to stderr() 
        """ 
        self._handle_results()
        self.finished.emit(exitcode)

    def stdout(self):
        """
        Returns the content of the stdout output, if any.
        """
        # TODO: should we check isRunning() before or can we rely on the "is not None" check?
        # A simpler approach would be to simply return self._stdout and have the caller interpret
        # the type of result: either None (job not completed) or a (potentially empty) string list
        # or the binary stream
        if self._stdout is not None:
            return self._stdout
        else:
            # TODO: Discuss what should happen here (job hasn't completed yet)
            return None

    def stderr(self):
        """
        Returns the content of the stderr output, if any.
        """
        # TODO: should we check isRunning() before or can we rely on the "is not None" check?
        if self._stderr is not none:
            return self._stderr
        else:
            # TODO: Discuss what should happen here (job hasn't completed yet)
            return None

    # TODO: is it a good place to keep this command
    # We can assume (can we?) the Git version not to change within a session,
    # so could there be a more global place where this information could be cached?
    def version(self):
        """
        Return git executable version.

        The version string is used to check, whether git executable exists and
        works properly. It may also be used to enable functions with newer git
        versions.

        Returns:
            tuple: PEP-440 conform git version (major, minor, patch)
        """
        if self._version:
            return self._version
        args = ['--version']
        # Query git version synchronously
        output = self.run_blocking(args) or ''
        # Parse version string like (git version 2.12.2.windows.1)
        match = re.match(r'git version (\d+)\.(\d+)\.(\d+)', output[0])
        if match:
            # PEP-440 conform git version (major, minor, patch)
            self._version = tuple(int(g) for g in match.groups())
            return self._version
        else:
            # TODO: Implement this case
            pass


class GitJobQueue(QObject):

    def __init__(self):
        super().__init__()
        self._queue = []

    def enqueue(self, gitjob):
        """ 
        Append 'Git instance' into the queue.
        If the queue is empty, the 'Git instacne' will run immediately.
        """   
        gitjob.executed.connect(self._auto_run_next)
        self._queue.append(gitjob)
        if len(self._queue) == 1:
            # args of Git process has been set in advance
            self._queue[0].run() 
    
    def killAll(self):
        """
        Kill all the process this queue contains
        Will be used when the file has lost focus.
        """
        self._remove_current()
        for job in self._queue:
            job.deleteLater()
        self._queue = []


    def _auto_run_next(self, execute_status):
        """
        To run next git process
        Triggered by the previous Git instance's executed signal.
        """
        self._remove_current()
        if self._queue:
            self._queue[0].run()

    def _remove_current(self):
        """
        Remove the Git() object in queue-head.
        If the Git() object is running, terminate it by calling kill()
        """
        if self._queue:
            if self._queue[0].isRunning():
                # prevent the git errorOccurred signals being handled
                self._queue[0].errorOccurred.disconnect()
                self._queue[0].kill()
            self._queue[0].deleteLater()    
            del self._queue[0]


 



