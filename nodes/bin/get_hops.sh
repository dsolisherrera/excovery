#!/bin/bash

HOSTNAME=$(hostname)
MESHNODES_A3="a3-005 a3-010 a3-012 a3-020 a3-020a a3-022 a3-023 a3-024 a3-025 a3-106 a3-119 a3-201 a3-206 a3-210"
MESHNODES_A6="a6-005 a6-008 a6-009 a6-010 a6-011 a6-015 a6-016 a6-017 a6-026a a6-026b a6-028 a6-031 a6-032a a6-032b a6-102 a6-107 a6-108a a6-108b a6-115 a6-122 a6-123 a6-124 a6-126 a6-127 a6-139 a6-141 a6-205 a6-207 a6-208 a6-212a a6-213 a6-214 a6-215 a6-ext-114 a6-ext-139 a6-ext-201"
MESHNODES_T9="t9-004a t9-004b t9-004c t9-006 t9-007 t9-009 t9-011 t9-018 t9-020 t9-022a t9-035 t9-040 t9-105 t9-106 t9-108 t9-111 t9-113 t9-117 t9-124 t9-134 t9-136 t9-137 t9-146 t9-147 t9-148 t9-149 t9-150 t9-154 t9-155 t9-157t t9-158 t9-160 t9-162 t9-163 t9-164 t9-165 t9-166 t9-169 t9-ext-110 t9-ext-121 t9-ext-150 t9-ext-154 t9-k21a t9-k21b t9-k23 t9-k36a t9-k36b t9-k38 t9-k40 t9-k44 t9-k46 t9-k48a t9-k48b t9-k60a t9-k60b t9-k61 t9-k63"

gethops() {
	for NODE in ${*}
	do
		echo -n "${HOSTNAME};${NODE};"
		traceroute -n ${NODE}-wlan2 | tail -1 | awk '{print $1}'
	done
}

case ${1} in
	a3) gethops ${MESHNODES_A3}
		;;
	a6) gethops ${MESHNODES_A6}
		;;
	t9) gethops ${MESHNODES_T9}
		;;
	all) gethops ${MESHNODES_A3}
		gethops ${MESHNODES_A6}
		gethops ${MESHNODES_T9}
		;;
	*)	echo "No nodes group given."
		;;
esac
