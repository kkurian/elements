import logging
import time

import pytest

from .test_framework.alice_and_bob import alice_and_bob
from .test_framework.blockchain.elements import Elements
from .test_framework.kill_elementsd_before_each_function import *  # noqa: E501, F401, F403
from .test_framework.wallet import Wallet


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('test_explorer_node')


def _wait_for(function):
    for _ in range(10):
        if not function():
            time.sleep(1)
        else:
            return
    raise TimeoutError


def test_slave_sees_all_blocks_and_transactions(blockchain):
    # All nodes on a blockchain see all transactions. Think of these
    # transactions as "proposed" lines in a giant public ledger book.
    with alice_and_bob(blockchain) as (alice, bob):
        with blockchain.node('slave') as slave:
            master = Wallet.master_node

            # Wait for master-slave connection.
            _wait_for(lambda: 1 == master.rpc('getinfo')['connections'])

            # Wait for slave to sync initial blockchain from master.
            last_block = master.rpc('listsinceblock')['lastblock']
            _wait_for(lambda: last_block == slave.rpc('listsinceblock')['lastblock'])  # noqa: E501

            # Ensure neither master nor slave have unconfirmed
            # transactions.
            #
            # N.B. Unconfirmed transactions existing prior to the slave-
            # master connection are not propagated. The test does not
            # make this apparent.
            assert 0 == len(master.rpc('getrawmempool'))
            assert 0 == len(slave.rpc('getrawmempool'))

            # Confirm that slave is aware of unconfirmed transactions.
            alice.transact(alice, bob, 10)
            rawmempool = master.rpc('getrawmempool')
            assert 0 < len(rawmempool)
            _wait_for(lambda: rawmempool == slave.rpc('getrawmempool'))

            # Verify that all transactions are confirmed in new block.
            assert None is master.generate_block()
            assert 0 == len(master.rpc('getrawmempool'))
            _wait_for(lambda: 0 == len(slave.rpc('getrawmempool')))

            # Wait for new block to propagate to slave.
            last_block = master.rpc('listsinceblock')['lastblock']
            _wait_for(lambda: last_block == slave.rpc('listsinceblock')['lastblock'])  # noqa: E501


def test_nodes_obey_the_same_rules(blockchain):
    # All nodes share a common set of rules about which transactions
    # should be approved and as a result what an expected or "validated
    # block" will look like given the current pending list of proposed
    # transactions.
    with alice_and_bob(blockchain) as (alice, bob):
        with blockchain.node('slave') as slave:
            master = Wallet.master_node

            # The master and slave nodes have the same signblockscript,
            # so they can validate blocks on a shared blockchain. Only
            # the master has had importprivkey called, so only the
            # master can sign blocks.
            #
            # Above, we have already demonstrated that blocks generated
            # by master are accepted by the slave. Here we demonstrate
            # that blocks generated by slave are not accepted by master.

            Wallet.master_node = slave  # submit transactions to slave

            # Watch for transactions involving alice and bob. This
            # enables the listunspent rpc on the slave for alice and
            # bob, which is used by Wallet to construct transactions.
            slave.rpc('importaddress', alice.address)
            slave.rpc('importaddress', bob.address)

            # Wait for master-slave connection.
            _wait_for(lambda: 1 == master.rpc('getinfo')['connections'])

            # Wait for slave to sync initial blockchain from master.
            last_block = master.rpc('listsinceblock')['lastblock']
            _wait_for(lambda: last_block == slave.rpc('listsinceblock')['lastblock'])  # noqa: E501

            # Alice submits a transaction to the slave.
            assert 0 == len(slave.rpc('getrawmempool'))
            alice.transact(alice, bob, 10)
            assert 0 < len(slave.rpc('getrawmempool'))

            # The slave, which does not possess the block signing key,
            # cannot generate a block.
            assert 'block-proof-invalid' == slave.generate_block()


def test_nodes_are_validators(blockchain):
    # Node forks if and when a created block violates the common set of
    # rules.
    if blockchain is Elements:
        # The Bitcoin network is existence proof of this. Also, above we
        # demonstrate that an Elements node without the signing key
        # cannot generate blocks.
        pass


@pytest.mark.skip(reason='Outside current requirements')
def test_multiple_signers(blockchain):
    # Support of up to x-of-3 multisig is standard.
    # See: https://github.com/ElementsProject/elements/blob/b979d442711c8c3f84d09c1b804af475616056d9/src/policy/policy.cpp#L46  # noqa: E501
    #
    # Also note: x-of-y is supported but non-standard. Non-standard
    # unconfirmed transactions (y > 3) do not propagate by default.
    raise NotImplementedError


@pytest.mark.xfail
def test_multiple_block_creators(blockchain):
    # TL;DR -- There is nothing to test in this case.
    #
    # Elements does not have native support for multiple block
    # creators.
    #
    #   - There are ways to build this functionality externally to the
    #     elements code base, but it is a non-trivial project.
    #
    #   - Elements claims to have this feature on their roadmap for
    #     June 2018, they previously estimated Q1 2018.
    #
    #   - Elements is considering allowing non-open source licensing
    #     of some of their technology to do this, and are "working
    #     on a proposal for us"
    raise NotImplementedError


def test_second_node_cannot_add_transactions(blockchain):
    with alice_and_bob(blockchain) as (alice, bob):
        with blockchain.node('slave') as slave:
            master = Wallet.master_node
            Wallet.master_node = slave  # submit transactions to slave

            # Watch for transactions involving alice and bob. This
            # enables the listunspent rpc on the slave for alice and
            # bob, which is used by Wallet to construct transactions.
            slave.rpc('importaddress', alice.address)
            slave.rpc('importaddress', bob.address)

            # Wait for master-slave connection.
            _wait_for(lambda: 1 == master.rpc('getinfo')['connections'])

            # Wait for slave to sync initial blockchain from master.
            last_block = master.rpc('listsinceblock')['lastblock']
            _wait_for(lambda: last_block == slave.rpc('listsinceblock')['lastblock'])  # noqa: E501

            # Alice submits to the slave a transaction, which fails to
            # propagate as an unconfirmed transaction to the master.
            assert 0 == len(master.rpc('getrawmempool'))
            assert 0 == len(slave.rpc('getrawmempool'))
            alice.transact(alice, bob, 10)
            rawmempool = slave.rpc('getrawmempool')
            assert 0 < len(rawmempool)
            with pytest.raises(TimeoutError):
                _wait_for(lambda: rawmempool == master.rpc('getrawmempool'))

            # The slave, which does not possess the block signing key,
            # cannot generate a block.
            assert 'block-proof-invalid' == slave.generate_block()
