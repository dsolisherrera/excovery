#!/bin/bash

for NODE in $* ; do
	ssh ${NODE} "~/bin/prepare.sh"
done
