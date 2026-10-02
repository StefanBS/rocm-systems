.. meta::
   :description: How to use the RCCL RAS diagnostics to compare GPU, driver, and NCCL configuration across the ranks of a job on AMD GPUs
   :keywords: RCCL, ROCm, AMD, RAS, diagnostics, NCCL_RUN_RAS_DIAGNOSTICS, rcclras, AMD SMI, ECC, XGMI, troubleshooting

.. _using-rccl-ras-diagnostics:

************************************************
Checking job configuration with RAS diagnostics
************************************************

The RAS (reliability, availability, and serviceability) subsystem of RCCL can
compare the configuration that every rank of a communicator reports and print a
short report. The report shows at a glance whether all ranks run with the same
``NCCL_*`` environment, driver version, and GPU configuration, which is a
common cause of hangs and performance differences in large jobs, and whether a
GPU reports memory errors or a down XGMI link.

This feature is inherited from NCCL 2.31 (RAS diagnostics). The checks only
collect and compare information. They do not send data between GPUs and do not
measure the network or the GPU links. To verify the GPU peer-to-peer data paths
on a node, use the active diagnostics (``NCCL_RUN_DIAGNOSTICS``) instead.

The report can be produced in two ways:

* At every communicator initialization, when ``NCCL_RUN_RAS_DIAGNOSTICS=1`` is
  set. See `Running at communicator initialization`_.
* On demand, at any time while the job runs, with the ``rcclras`` client. See
  `Running on demand`_.

Checks on AMD GPUs
==================

The report has one result per check and communicator:

* **GPU inventory:** compares the number of AMD GPUs on each node and the model
  of the GPU used by each rank.
* **HIP driver version:** compares the driver version that the HIP runtime
  reports (``hipDriverGetVersion``) across the ranks.
* **ECC:** reports the ranks whose GPU has uncorrectable or deferred ECC
  errors. With ``NCCL_DIAGNOSTICS_ECC_THRESHOLD`` set, it also reports the
  ranks whose GPU has at least that many correctable errors.
* **XGMI:** compares the number of AMD Infinity Fabric (XGMI) links of the GPU
  used by each rank and reports the ranks whose GPU has a link that is down.
  Disabled links are not counted. A system without XGMI links prints no line.
* **NCCL environment:** compares the names and values of all ``NCCL_*``
  environment variables across the ranks and lists the ranks of every value
  that differs.

The GPU inventory, ECC, and XGMI checks read AMD SMI (``libamd_smi.so``), the
same source as the ``amd-smi`` tool. With ``NCCL_RUN_RAS_DIAGNOSTICS=1``, RCCL
loads the library when the process creates its first communicator; otherwise,
the first time the diagnostics run. This does not depend on the value of
``RCCL_USE_AMD_SMI_LIB``. The ECC check
uses the error totals of all memory blocks of the GPU, which ``amd-smi metric
--ecc`` shows per block. Use ``amd-smi`` to inspect a GPU that the report
names, for example ``amd-smi metric --ecc`` and ``amd-smi xgmi``.

If AMD SMI cannot be loaded or does not answer for a GPU, the check reports
``unavailable via AMD SMI``. Such results are tagged ``[INFO]`` and do not
indicate a problem with the system. Set ``NCCL_DEBUG=INFO`` and
``NCCL_DEBUG_SUBSYS=RAS`` to log the AMD SMI query that failed.

Prerequisites
=============

RAS diagnostics need the RAS subsystem, which is enabled by default
(``NCCL_RAS_ENABLE=1``). With ``NCCL_RAS_ENABLE=0``, a communicator created
with ``NCCL_RUN_RAS_DIAGNOSTICS=1`` prints the report header, but no check runs
and no ``completed`` line follows.

The RAS threads of all processes of the job listen for client connections on
``localhost``, port ``28028``. Set ``NCCL_RAS_ADDR`` to change the address, for
example when several jobs share a node. See
`Running on demand on a shared node`_.

Running at communicator initialization
======================================

Initialization-time diagnostics are disabled by default. Set
``NCCL_RUN_RAS_DIAGNOSTICS=1`` for every process of the job:

.. code:: shell

   NCCL_RUN_RAS_DIAGNOSTICS=1 <application> [arguments]

For example, with rccl-tests:

.. code:: shell

   NCCL_RUN_RAS_DIAGNOSTICS=1 ./build/all_reduce_perf -b 8 -e 128M -f 2 -g 8

The diagnostics run at every communicator initialization, including
``ncclCommInitRank``, ``ncclCommInitAll``, and ``ncclCommSplit``. Each report
covers only the new communicator, and an application that creates several
communicators prints one report per communicator.

The report is printed to the standard output of the process that hosts rank 0
of the communicator, not to ``NCCL_DEBUG_FILE``. That process prints the
header while the communicator is being created. The results and the
``completed`` line follow from the RAS thread shortly after, usually after
the initialization call has returned. If a process exits or destroys the
communicator right after creating it, the report can be incomplete.

Diagnostics are informational. A reported difference does not make
communicator initialization fail, and the communicator remains usable.

Running on demand
=================

Request a report from a running job with the ``-D`` option of the ``rcclras``
client, on any node of the job. The request does not depend on
``NCCL_RUN_RAS_DIAGNOSTICS``:

.. code:: shell

   rcclras -D
   rcclras -h <host> -p <port> -D

``rcclras`` is installed with RCCL, in the ``bin`` directory of the ROCm
installation. Without a client binary, send the ``DIAGNOSTICS`` command of the
RAS text protocol, for example with netcat:

.. code:: shell

   echo diagnostics | nc localhost 28028

The report covers every communicator known to the RAS threads of the job and is
returned over the client connection. It is printed by ``rcclras``, not by the
application. The report is available in text format only: with
``rcclras -D -f json``, the job replies
``ERROR: diagnostics only supports text output``.

Request a report after every rank has finished creating its communicators. An
earlier request covers only the ranks that RAS already knows about, and reports
the others as incomplete or misses them.

Running on demand on a shared node
----------------------------------

RAS processes of the same user share the client port. If another user's job on
the same node already listens on the port, the RAS threads of your job cannot
listen on it, and ``rcclras`` silently connects to the other job instead. This
can happen when containers use the host network. The only sign of the conflict
is a ``RAS failed to establish a client listening socket`` message, which is
printed with ``NCCL_DEBUG=INFO``.

To avoid the conflict, choose a free port for the job and pass the same port to
the client:

.. code:: shell

   export NCCL_RAS_ADDR=localhost:<port>
   rcclras -p <port> -D

The client port does not check who connects. Any local user who can reach the
port can request a report, which includes the names and values of ``NCCL_*``
variables that differ across ranks. Keep ``NCCL_RAS_ADDR`` on ``localhost``
unless remote access is required.

Reading the report
==================

Every line starts with ``<hostname>:<pid> NCCL DIAG``. A report consists of a
header, the results grouped by check and communicator, and a ``completed``
line. An initialization-time report on an 8-GPU AMD Instinct MI355X node, with
one process per GPU, looks like this:

.. code:: none

   node01:4242 NCCL DIAG === RAS Diagnostics ===
   node01:4242 NCCL DIAG [OK]   GPU inventory: 8x AMD Instinct MI355X per node consistent across 8 ranks in comm 0x5fa31c27a9e0d1b4
   node01:4242 NCCL DIAG [OK]   HIP driver version: 71526333 consistent across 8 ranks in comm 0x5fa31c27a9e0d1b4
   node01:4242 NCCL DIAG [OK]   ECC: no uncorrected volatile errors across 8 ranks in comm 0x5fa31c27a9e0d1b4
   node01:4242 NCCL DIAG [OK]   XGMI: found 7 link(s) per device, all active across 8 ranks in comm 0x5fa31c27a9e0d1b4
   node01:4242 NCCL DIAG [OK]   NCCL environment: NCCL_* env vars consistent across 8 ranks in comm 0x5fa31c27a9e0d1b4
   node01:4242 NCCL DIAG RAS diagnostics completed in 38.4 ms across 8 ranks

The ``completed`` line of an initialization-time report counts the ranks of
the communicator. The ``completed`` line of an on-demand report counts the RAS
peers that answered, that is, the processes of the job, for example
``across 16 RAS peers`` for two nodes with one process per GPU.

Result lines use two tags:

* ``[OK]`` means that the check found no difference across the ranks and, for
  the ECC and XGMI checks, no error and no down link.
* ``[INFO]`` marks a difference, an ECC error or down link, incomplete
  information, or a check whose data is unavailable. Read the message text to
  tell them apart.

A check that finds a difference prints several lines that group the ranks by
value. For example, a job where the processes on the second node run with a
different ``NCCL_BUFFSIZE``:

.. code:: none

   node01:4242 NCCL DIAG [INFO] NCCL environment: mismatch across 16 ranks in comm 0x5fa31c27a9e0d1b4 for NCCL_BUFFSIZE
   node01:4242 NCCL DIAG [INFO] NCCL environment: NCCL_BUFFSIZE=(unset) on rank(s) {0,1,2,3,4,5,6,7}
   node01:4242 NCCL DIAG [INFO] NCCL environment: NCCL_BUFFSIZE=8388608 on rank(s) {8,9,10,11,12,13,14,15}
   node01:4242 NCCL DIAG [INFO] NCCL environment: 1 NCCL_* env var(s) differ across ranks in comm 0x5fa31c27a9e0d1b4

Rank lists contain a limited number of entries. A longer list ends with an
ellipsis and the total number of ranks in the group.

Variables that legitimately differ between processes, such as a per-process
``NCCL_DEBUG_FILE``, are reported in the same way. Compare the listed
variables with the configuration you intended.

If not every rank answered, for example because a process stopped responding,
the result reads ``diagnostics incomplete, gathered <n>/<total> ranks`` and
names the communicator.
