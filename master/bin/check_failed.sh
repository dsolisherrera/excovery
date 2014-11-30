#!/bin/bash

if [ "x${1}" == "x" ]
then
	echo "Please give experiment directory or "
	exit
else
	EXPDIR="$1"
fi

NEEDED="1000"
RUNS_TOTAL="0"
RUNS_TOTAL_VALID="0"

for EXP_DB in $(find ${EXPDIR} -maxdepth 2 -type f -name "*.sqlite")
do
	EXP="$(basename ${EXP_DB} .sqlite)"
	
	NUM_NODES=$(sqlite3 ${EXP_DB} << EOF
select count (distinct NodeID) from ExtraRunMeasurements;
EOF
	)
	
	RUNS_COMPLETE=$(sqlite3 ${EXP_DB} << EOF
SELECT * FROM run_ids;
EOF
	)
	RUN_SETS=$((for RUN in ${RUNS_COMPLETE}; do echo ${RUN} ; done) | sed 's/^[0-9]*\|\(run_[0-9]*_[0-9]*_[0-9]*\)_[0-9]*$/\1/' | sort | uniq)
	
	for RUN_SET in ${RUN_SETS}
	do
		RUNS=$(sqlite3 ${EXP_DB} << EOF
SELECT COUNT(*) FROM run_ids where run_identifier like "${RUN_SET}%";
EOF
		)
	
		FAILS=$(sqlite3 ${EXP_DB} << EOF
select distinct RunID from ExtraRunMeasurements where RunID in (SELECT runID from run_ids where run_identifier like "${RUN_SET}%") and NodeID in (SELECT NodeID FROM Events WHERE (RunID = "1" and Parameter = "actor
")) and Name = "routes" and Content = "fail
";
EOF
		)
		for FAIL in ${FAILS}
		do
			FAILNODES=$(sqlite3 ${EXP_DB} << EOF
select NodeID from ExtraRunMeasurements where RunID = ${FAIL} and NodeID in (SELECT NodeID FROM Events WHERE (RunID = ${FAIL} and Parameter = "actor
")) and Name = "routes" and Content = "fail
";
EOF
			)
			FAILNODESCNT=$(sqlite3 ${EXP_DB} << EOF
select count (distinct NodeID) from ExtraRunMeasurements where RunID = ${FAIL} and NodeID in (SELECT NodeID FROM Events WHERE (RunID = ${FAIL} and Parameter = "actor
")) and Name = "routes" and Content = "fail
";
EOF
			)
			#echo "Run ${FAIL}: ${FAILNODESCNT} Nodes ($(for i in ${FAILNODES}; do echo -n $i' ' ; done))"
		done
	
		FAILS=$(sqlite3 ${EXP_DB} << EOF
select count (distinct RunID) from ExtraRunMeasurements where RunID in (SELECT runID from run_ids where run_identifier like "${RUN_SET}%") and NodeID in (SELECT NodeID FROM Events WHERE (RunID = "1" and Parameter = "actor
")) and Name = "routes" and Content = "fail
";
EOF
		)
		echo "Experiment: ${EXP} Set: ${RUN_SET} Runs: ${RUNS} Fails: ${FAILS}, Nodes: ${NUM_NODES}"
		
		OK=$(expr ${RUNS} - ${FAILS})
		if [ ${OK} -lt ${NEEDED} ]
		then
			echo "${OK}/${RUNS} runs ok, increase to $(expr ${NEEDED} - ${OK} + ${RUNS}) needed."
		else
			echo "${OK}/${RUNS} runs ok"
		fi
		RUNS_TOTAL_VALID=$((${RUNS_TOTAL_VALID} + ${OK}))
		RUNS_TOTAL=$((${RUNS_TOTAL} + ${RUNS}))
	done
done

echo "Total Runs: ${RUNS_TOTAL} (${RUNS_TOTAL_VALID} valid)"
