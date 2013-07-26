#!/bin/bash -e
# ============================================
#  celeryd - Starts the Celery worker daemon.
# ============================================
#
# :Usage: /etc/init.d/celeryd {start|stop|force-reload|restart|try-restart|status}
# :Configuration file: /etc/default/celeryd-nationwide
#
# See http://docs.celeryq.org/en/latest/cookbook/daemonizing.html#init-script-celeryd


### BEGIN INIT INFO
# Provides:          celeryd
# Required-Start:    $network $local_fs $remote_fs
# Required-Stop:     $network $local_fs $remote_fs
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
# Short-Description: celery task worker daemon
### END INIT INFO

#set -e

DEFAULT_PID_FILE="/var/run/celeryd@%n.pid"
DEFAULT_LOG_FILE="/var/log/celery/celeryd@%n.log"
DEFAULT_LOG_LEVEL="ERROR"
DEFAULT_NODES="celery"
DEFAULT_CELERYD="-m celery.bin.celeryd_detach"
CELERYD_USER="celery"
CELERYD_GROUP="celery"


# /etc/init.d/celeryd: start and stop the celery task worker daemon.

CELERY_DEFAULTS=${CELERY_DEFAULTS:-"/etc/default/celeryd.default.rb"}

test -f "$CELERY_DEFAULTS" && . "$CELERY_DEFAULTS"
if [ -f "/etc/default/celeryd-nationwide" ]; then
    . /etc/default/celeryd-nationwide
fi

CELERYD_PID_FILE=${CELERYD_PID_FILE:-${CELERYD_PIDFILE:-$DEFAULT_PID_FILE}}
CELERYD_LOG_FILE=${CELERYD_LOG_FILE:-${CELERYD_LOGFILE:-$DEFAULT_LOG_FILE}}
CELERYD_LOG_LEVEL=${CELERYD_LOG_LEVEL:-${CELERYD_LOGLEVEL:-$DEFAULT_LOG_LEVEL}}
CELERYD_MULTI=${CELERYD_MULTI:-"celeryd-multi"}
CELERYD=${CELERYD:-$DEFAULT_CELERYD}
CELERYCTL=${CELERYCTL:="celeryctl"}
CELERYD_NODES=${CELERYD_NODES:-$DEFAULT_NODES}

export CELERY_LOADER

if [ -n "$2" ]; then
    CELERYD_OPTS="$CELERYD_OPTS $2"
fi

CELERYD_LOG_DIR=`dirname $CELERYD_LOG_FILE`
CELERYD_PID_DIR=`dirname $CELERYD_PID_FILE`
if [ ! -d "$CELERYD_LOG_DIR" ]; then
    mkdir -p $CELERYD_LOG_DIR
fi
if [ ! -d "$CELERYD_PID_DIR" ]; then
    mkdir -p $CELERYD_PID_DIR
fi

# Extra start-stop-daemon options, like user/group.
if [ -n "$CELERYD_USER" ]; then
    DAEMON_OPTS="$DAEMON_OPTS --uid=$CELERYD_USER"
    chown "$CELERYD_USER" $CELERYD_LOG_DIR $CELERYD_PID_DIR
fi
if [ -n "$CELERYD_GROUP" ]; then
    DAEMON_OPTS="$DAEMON_OPTS --gid=$CELERYD_GROUP"
    chgrp "$CELERYD_GROUP" $CELERYD_LOG_DIR $CELERYD_PID_DIR
fi

if [ -n "$CELERYD_CHDIR" ]; then
    DAEMON_OPTS="$DAEMON_OPTS --workdir=\"$CELERYD_CHDIR\""
fi


check_dev_null() {
    if [ ! -c /dev/null ]; then
        echo "/dev/null is not a character device!"
        exit 1
    fi
}


export PATH="${PATH:+$PATH:}/usr/sbin:/sbin"


stop_workers () {
    $CELERYD_MULTI stop $CELERYD_NODES --pidfile="$CELERYD_PID_FILE"
}


start_workers () {
    $CELERYD_MULTI start $CELERYD_NODES $DAEMON_OPTS        \
                         --pidfile="$CELERYD_PID_FILE"      \
                         --logfile="$CELERYD_LOG_FILE"      \
                         --loglevel="$CELERYD_LOG_LEVEL"    \
                         --cmd="$CELERYD"                   \
                         $CELERYD_OPTS
}


restart_workers () {
    $CELERYD_MULTI restart $CELERYD_NODES $DAEMON_OPTS      \
                           --pidfile="$CELERYD_PID_FILE"    \
                           --logfile="$CELERYD_LOG_FILE"    \
                           --loglevel="$CELERYD_LOG_LEVEL"  \
                           --cmd="$CELERYD"                 \
                           $CELERYD_OPTS
}



case "$1" in
    start)
        check_dev_null
        start_workers
    ;;

    stop)
        check_dev_null
        stop_workers
    ;;

    reload|force-reload)
        echo "Use restart"
    ;;

    status)
        $CELERYCTL status $CELERYCTL_OPTS
    ;;

    restart)
        check_dev_null
        restart_workers
    ;;

    try-restart)
        check_dev_null
        restart_workers
    ;;

    *)
        echo "Usage: /etc/init.d/celeryd {start|stop|restart|try-restart|kill}"
        exit 1
    ;;
esac

exit 0