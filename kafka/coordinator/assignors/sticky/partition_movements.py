import logging
from collections import defaultdict
from copy import deepcopy
from typing import Dict, Set, List, Tuple, NamedTuple

from kafka.structs import TopicPartition

log = logging.getLogger(__name__)


class ConsumerPair(NamedTuple):
    """
    Represents a pair of Kafka consumer ids involved in a partition reassignment.
    Each ConsumerPair corresponds to a particular partition or topic, indicates that the particular partition or some
    partition of the particular topic was moved from the source consumer to the destination consumer
    during the rebalance. This class helps in determining whether a partition reassignment results in cycles among
    the generated graph of consumer pairs.
    """
    src_member_id: str
    dst_member_id: str


def is_sublist(source: List, target: Tuple) -> bool:
    """Checks if one list is a sublist of another.

    Arguments:
      source: the list in which to search for the occurrence of target.
      target: the list to search for as a sublist of source

    Returns:
      true if target is in source; false otherwise
    """
    for index in (i for i, e in enumerate(source) if e == target[0]):
        if tuple(source[index: index + len(target)]) == target:
            return True
    return False


class PartitionMovements:
    """
    This class maintains some data structures to simplify lookup of partition movements among consumers.
    At each point of time during a partition rebalance it keeps track of partition movements
    corresponding to each topic, and also possible movement (in form a ConsumerPair object) for each partition.
    """

    def __init__(self):
        self.partition_movements_by_topic: Dict[str, Dict[ConsumerPair, Set[TopicPartition]]] = defaultdict(
            lambda: defaultdict(set)
        )
        self.partition_movements: Dict[TopicPartition, ConsumerPair] = {}

    def move_partition(self, partition: TopicPartition, old_consumer: str, new_consumer: str):
        pair = ConsumerPair(src_member_id=old_consumer, dst_member_id=new_consumer)
        if partition in self.partition_movements:
            # this partition has previously moved
            existing_pair = self._remove_movement_record_of_partition(partition)
            assert existing_pair.dst_member_id == old_consumer
            if existing_pair.src_member_id != new_consumer:
                # the partition is not moving back to its previous consumer
                self._add_partition_movement_record(
                    partition, ConsumerPair(src_member_id=existing_pair.src_member_id, dst_member_id=new_consumer)
                )
        else:
            self._add_partition_movement_record(partition, pair)

    def get_partition_to_be_moved(self, partition: TopicPartition, old_consumer: str, new_consumer: str):
        if partition.topic not in self.partition_movements_by_topic:
            return partition
        if partition in self.partition_movements:
            # this partition has previously moved
            assert old_consumer == self.partition_movements[partition].dst_member_id
            old_consumer = self.partition_movements[partition].src_member_id
        reverse_pair = ConsumerPair(src_member_id=new_consumer, dst_member_id=old_consumer)
        if reverse_pair not in self.partition_movements_by_topic[partition.topic]:
            return partition

        return self.partition_movements_by_topic[partition.topic][reverse_pair].pop()

    def are_sticky(self) -> bool:
        for topic, movements in self.partition_movements_by_topic.items():
            movement_pairs = set(movements.keys())
            if self._has_cycles(movement_pairs):
                log.error(
                    f"Stickiness is violated for topic {topic}\n"
                    f"Partition movements for this topic occurred among the following consumer pairs:\n"
                    f"{movement_pairs}"
                )
                return False
        return True

    def _remove_movement_record_of_partition(self, partition: TopicPartition) -> ConsumerPair:
        pair = self.partition_movements[partition]
        del self.partition_movements[partition]
        self.partition_movements_by_topic[partition.topic][pair].remove(partition)

        return pair

    def _add_partition_movement_record(self, partition: TopicPartition, pair: ConsumerPair):
        self.partition_movements[partition] = pair
        self.partition_movements_by_topic[partition.topic][pair].add(partition)

    def _has_cycles(self, consumer_pairs: Set[ConsumerPair]):
        cycles = set()
        for pair in consumer_pairs:
            reduced_pairs = deepcopy(consumer_pairs)
            reduced_pairs.remove(pair)
            path = [pair.src_member_id]
            if self._is_linked(pair.dst_member_id, pair.src_member_id, reduced_pairs, path) and not self._is_subcycle(
                path, cycles
            ):
                cycles.add(tuple(path))
                log.error(f"A cycle of length {len(path) - 1} was found: {path}")

        # for now we want to make sure there is no partition movements of the same topic between a pair of consumers.
        # the odds of finding a cycle among more than two consumers seem to be very low (according to various randomized
        # tests with the given sticky algorithm) that it should not worth the added complexity of handling those cases.
        for cycle in cycles:
            if len(cycle) == 3:  # indicates a cycle of length 2
                return True
        return False

    @staticmethod
    def _is_subcycle(cycle: List[str], cycles: Set[Tuple[str]]) -> bool:
        super_cycle = deepcopy(cycle)
        super_cycle = super_cycle[:-1]
        super_cycle.extend(cycle)
        for found_cycle in cycles:
            if len(found_cycle) == len(cycle) and is_sublist(super_cycle, found_cycle):
                return True
        return False

    def _is_linked(self, src: str, dst: str, pairs: Set[ConsumerPair], current_path: List[str]):
        if src == dst:
            return False
        if not pairs:
            return False
        if ConsumerPair(src, dst) in pairs:
            current_path.append(src)
            current_path.append(dst)
            return True
        for pair in pairs:
            if pair.src_member_id == src:
                reduced_set = deepcopy(pairs)
                reduced_set.remove(pair)
                current_path.append(pair.src_member_id)
                return self._is_linked(pair.dst_member_id, dst, reduced_set, current_path)
        return False
