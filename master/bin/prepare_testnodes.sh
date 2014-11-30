#!/bin/bash

/usr/bin/dsh -f ~/nodefiles/testnodes -M -c "~/bin/prepare-testnodes.sh"
/usr/bin/dsh -f ~/nodefiles/testnodes -M -c "~/bin/check.sh"
