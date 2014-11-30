#!/bin/bash

# script to check whether an experiment run is still making progress or not

previous="tmp/monitor_base.temp"
current="tmp/status_now.temp"
dir_to_monitor=$(pwd)/MasterResults/${EXP_NAME}
EXP_NAME=$(basename $(pwd))

MY_MAIL="andreas.dittrich@usi.ch"
#MY_MAIL="cotobj@usi.ch"
INTERVAL=300

status_mail() {
	case ${1} in
		hang)		BODY="This was detected on $(date)."
				SUBJECT="Experiment ${EXP_NAME} hasnt been updated in the last ${INTERVAL} seconds"
				;;
		*)	echo "wrong parameter."
				;;
	esac
	echo "${BODY}" | mail -s "${SUBJECT}" ${MY_MAIL}
}


while true ; do
	if [ ! -e $previous ] ;then
		mkdir tmp
	fi
	find "$dir_to_monitor" |sort > $previous
	sleep $INTERVAL
	find "$dir_to_monitor" |sort > $current
	if diff $current $previous >/dev/null ; then
	  echo Same
	  status_mail "hang"
  	else 
	       echo different	
	fi
done
