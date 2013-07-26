# Name of nodes to start, here we have a single node
CELERYD_NODES="w1"
# or we could have three nodes:
#CELERYD_NODES="w1 w2 w3"

USER_HOME="/home/admin"

VIRTUAL_ENV_DIR="$USER_HOME/.virtualenvs/referralbuddy"

# Where to chdir at start.
CELERYD_CHDIR="/opt/referralbuddy/current"

# Python interpreter from environment.
ENV_PYTHON="$VIRTUAL_ENV_DIR/bin/python"

# How to call "manage.py celeryd_multi"
CELERYD_MULTI="$ENV_PYTHON $CELERYD_CHDIR/manage.py celeryd_multi"

# How to call "manage.py celeryctl"
CELERYCTL="$ENV_PYTHON $CELERYD_CHDIR/manage.py celeryctl"

# Extra arguments to celeryd
CELERYD_OPTS="--time-limit=300 --concurrency=8"

# Name of the celery config module.
CELERY_CONFIG_MODULE="celeryconfig"

# %n will be replaced with the nodename.
CELERYD_LOG_FILE="/var/log/celery/%n.log"
CELERYD_PID_FILE="/var/run/celery/%n.pid"

# Workers should run as an unprivileged user.
CELERYD_USER="celery"
CELERYD_GROUP="celery"

CELERYBEAT_USER="celery"
CELERYBEAT_GROUP="celery"

# Name of the projects settings module.
export DJANGO_SETTINGS_MODULE="pages.settings"

CELERYBEAT = "$ENV_PYTHON $CELERYD_CHDIR/manage.py celerybeat"