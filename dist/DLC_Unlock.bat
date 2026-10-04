@echo off
pushd %~dp0

cd support
InstallDLC.exe /VERYSILENT
InstallSampleMaps.exe /VERYSILENT
M2CollectionDLCRepair.exe /VERYSILENT
cd ..

popd
