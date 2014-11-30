#!/bin/bash

# /usr/bin/dsh -f <( for i in ${*} ; do echo ${i} ; done ) -M -c 'export LANG=C ; \
#     /sbin/ifconfig bmf0 | \
# 	grep -e "inet addr" | cut -d: -f2 | cut -d" " -f1' | \
#     awk -F: '{\
#         gsub(/^ */, "", $2); \
#         printf "\t\t\t<spec_env_map id=\"%s\" ip=\"%s\" />\n", $1, $2\
#     }'

if [ -a ${1} ]
then
	/usr/bin/dsh -f ${1} -M -c 'export LANG=C ; \
		/sbin/ifconfig bmf0 | \
		grep -e "inet addr" | cut -d: -f2 | cut -d" " -f1'
else
	/usr/bin/dsh -f <( for i in ${*} ; do echo ${i} ; done ) -M -c 'export LANG=C ; \
		/sbin/ifconfig bmf0 | \
		grep -e "inet addr" | cut -d: -f2 | cut -d" " -f1'
fi

