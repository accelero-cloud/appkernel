#!/usr/bin/env bash

#!/bin/bash
#
# init.d script with LSB support.
#
# Copyright (c) 2007 Javier Fernandez-Sanguino <jfs@debian.org>
#
# This is free software; you may redistribute it and/or modify
# it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2,
# or (at your option) any later version.
#
# This is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License with
# the Debian operating system, in /usr/share/common-licenses/GPL;  if
# not, write to the Free Software Foundation, Inc., 59 Temple Place,
# Suite 330, Boston, MA 02111-1307 USA
#
### BEGIN INIT INFO
# Provides:          $SERVICE_NAME
# Required-Start:    {{ service.required.start }}
# Required-Stop:     {{ service.required.stop }}
# Should-Start:      {{ service.should.start }}
# Should-Stop:       {{ service.should.stop }}
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
# Short-Description: {{ service.description.short }}
# Description:       {{ service.description.detailed }}
### END INIT INFO

## Once installed, run: update-rc.d {{ service.name }} defaults

. /lib/lsb/init-functions
SERVICE_NAME="appkernel"
PACKAGE_NAME="appkernel"
PIP=`which pip`
LOGGER="`which logger` -t ${SERVICE_NAME}"
PIDFILE="/var/run/${SERVICE_NAME}.pid"
KILL_TIMEOUT=30
PORT=5000
USER=appkernel
HOME=/opt/${SERVICE_NAME}
source  ${HOME}/venv/bin/activate

running() {
    # Check if the process is running looking at /proc
    # (works for all users)

    # No pidfile, probably no daemon present
    [ ! -f "${PIDFILE}" ] && return 1
    pid=`cat ${PIDFILE}`
    running_pid ${pid} ${DAEMON} || return 1
    return 0
}

start() {
    log_daemon_msg "Starting ${SERVICE_NAME}"
    ${LOGGER} "starting $SERVICE_NAME"
    cd $HOME
    if [ -z $(which ${SERVICE_NAME}) ]; then
        log_daemon_msg "deploying new version of $SERVICE_NAME"
        ${LOGGER} "deploying new version of $SERVICE_NAME"
    fi

    start-stop-daemon --start --background --make-pidfile --pidfile ${PIDFILE} --chuid ${USER} --chdir $HOME --startas `which ${SERVICE_NAME}` -- -c /etc/${SERVICE_NAME} 2>&1
    res=$?
    [ ${res} -eq 1 ] &&  log_warning_msg "$SERVICE_NAME is already running..." || :
    return ${res}
}

status() {
    start-stop-daemon --status --pidfile ${PIDFILE} --chuid ${USER}
    case $? in
        0)
            echo "$SERVICE_NAME is running."
        ;;
        1)
            echo "$SERVICE_NAME is not running and pid file exists"
        ;;
        2)
            echo "$SERVICE_NAME is not running and lock file exists"
        ;;
        3)
            echo "$SERVICE_NAME is not running"
        ;;
        4)
            echo "$SERVICE_NAME status is unknown"
        ;;
        *)
            echo "return code $? is not supported"
        ;;
    esac
}

stop() {
    log_daemon_msg "Stopping $SERVICE_NAME"
    start-stop-daemon --stop --pidfile ${PIDFILE} --chuid ${USER} --retry ${KILL_TIMEOUT} 2>&1
    res=$?
    [ ${res} -eq 1 ] &&  log_warning_msg "$SERVICE_NAME was not running or the pidfile is deleted." || :
    return ${res}
}

force_stop() {
# Force the process to die killing it manually
  [ ! -e "$PIDFILE" ] && return
  if running ; then
    kill -15 $pid
  # Is it really dead?
    sleep "$KILL_TIMEOUT"s
    if running ; then
      kill -9 $pid
      sleep "$KILL_TIMEOUT"s
      if running ; then
        log_warning_msg "Cannot kill $NAME (pid=$pid)!"
        exit 1
      fi
    fi
  fi
  rm -f ${PIDFILE}
}

download() {
    log_daemon_msg "using branch:\t $BRANCH"
    cd $HOME
    res_msg=$(${PIP} install --upgrade ${PACKAGE_NAME} 2>&1)
    res=$?
    [ "$res" = "1" ] && log_failure_msg ${res_msg} || :
    return ${res}
}

wait() {
    if [ ! -f ${PIDFILE} ]; then
        echo "${PIDFILE} not found..."
    else
        pid=`cat ${PIDFILE}`
        while [ -e /proc/${pid} ]
        do
            log_warning_msg "Process: $PID is still running"
            sleep .6
        done
        log_daemon_msg "Process $PID has finished"
    fi
}

show_help() {
        echo -e "command parameters:\n"
        echo -e "\tstart - start the process if not started already"
        echo -e "\tstop - stop the process if not stopped already"
        echo -e "\tstatus - checks the running status of the process"
        echo -e "\trestart - restart the service"
        echo -e "\tdeploy - download and restarts the service"
        echo -e "\thelp - this help text"
}

case $1 in
    start)
        start
    ;;
    stop)
        stop
    ;;
    force-stop)
        # First try to stop gracefully the program
        $0 stop
        if running; then
            # If it's still running try to kill it more forcefully
            log_daemon_msg "Stopping (force) $DESC" "$NAME"
      errcode=0
            force_stop || errcode=$?
            log_end_msg ${errcode}
        fi
    ;;
    status)
        status
    ;;
    download)
        download
    ;;
    restart)
        stop
        wait
        start
    ;;
    deploy)
        download
        if [ "$?" != "1" ]; then
            stop
            wait
            start
        else
            log_warning_msg "aborting deployment due to download error."
            exit -1
        fi
    ;;
    help)
        show_help
    ;;
    reload)
        log_warning_msg "Reloading $SERVICE_NAME daemon: not implemented."
        log_warning_msg "Use restart."
        ;;
    *)
        echo "command parameter [$1] is not supported, running help.\n"
        show_help
    ;;
esac