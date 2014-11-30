#!/bin/bash

# Usage info
show_help() {
cat << EOF
Usage: ${0##*/} [-hv] [-i SECONDS] [-m EMAIL] [-n NAME]
Check for routes on actors. This script periodically checks for routes on
(actor-)nodes in a given nodefile. Can be run during experiments to check
whether the actors are still connected to the network. Recovers from
intermediate errors, in case routes are only lost shortly.

    -h             display this help and exit
    -e "N1 N2 ..." exclude specific nodes from check
    -i SECONDS     check interval in seconds
    -m EMAIL       email address to send status reports to
    -n NAME        experiment identifier
    -v             verbose mode. Can be used multiple times for increased
                   verbosity.
EOF
}				

get_actors() {
	ACTORS=$( \
		awk '/spec_actor_map/ { \
			sub(/^.* id="/, "") ; \
			split($0, node, "\"") ; \
			print node[1] \
		}' ${EXP_DESC} \
	)
	for EXCLUDE in ${EXCLUDES} ; do
		ACTORS=$(echo ${ACTORS} | sed s/${EXCLUDE}//)
	done
	for ACTOR in ${ACTORS} ; do echo ${ACTOR} ; done
}

check_actors() {
	/usr/bin/dsh -f <( get_actors ) -M -c "~/bin/check.sh >/dev/null 2>&1"
}

status_mail() {
	case ${1} in
		up)		BODY="This was detected on $(date)."
				SUBJECT="Experiment ${EXP_NAME} routes are up"
				;;
		down)	BODY="This was detected on $(date). Think about restarting experiment."
				SUBJECT="Experiment ${EXP_NAME} routes are down"
				;;
		*)	echo "wrong parameter."
				;;
	esac
	echo "${BODY}" | mail -s "${SUBJECT}" ${MY_MAIL}
}

# Initialize our own variables:
VERBOSE=0
MY_MAIL="andreas.dittrich@usi.ch"
EXP_NAME=$(basename $(pwd))
EXP_DESC=${EXP_NAME}.xml
INTERVAL=60

OPTIND=1 # Reset is necessary if getopts was used previously in the script.  It is a good idea to make this local in a function.
while getopts "hve:m:n:ix:" OPT; do
	case "${OPT}" in
		h)	show_help
			exit 0
			;;
		v)	VERBOSE=1
			;;
		e)	EXCLUDES=${OPTARG}
			;;
		m)	MY_MAIL=${OPTARG}
			;;
		n)	EXP_NAME=${OPTARG}
			;;
		i)	INTERVAL=${OPTARG}
			;;
		x)	EXP_DESC=${OPTARG}
			;;
		'?')show_help >&2
			exit 1
			;;
	esac
done
shift "$((OPTIND-1))" # Shift off the options and optional --.

if [ ! -f ${EXP_DESC} ] ; then
	echo "ERROR: XML description not found." >&2
	exit 1
fi

while true ; do
	check_actors
	if [ $? -ne 0 ] ; then
		status_mail "down"
		while true ; do
			check_actors
			if [ $? -eq 0 ] ; then
				status_mail "up"
				break
			fi
			sleep ${INTERVAL}
		done
	fi
	sleep ${INTERVAL}
done
