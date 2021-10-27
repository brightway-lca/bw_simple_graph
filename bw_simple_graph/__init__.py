import datetime
import itertools
import os
from pathlib import Path

import numpy as np
from bw_processing import (
    INDICES_DTYPE,
    clean_datapackage_name,
    create_datapackage,
    load_datapackage,
    safe_filename,
)
from fs.zipfs import ZipFS
from peewee import (
    DateTimeField,
    DoesNotExist,
    FloatField,
    ForeignKeyField,
    Model,
    PostgresqlDatabase,
    TextField,
)

__version__ = (0, 1)

cache_dir = Path(os.environ.get("BW_SIMPLE_CACHE"))
assert cache_dir.is_dir()

pg_db = PostgresqlDatabase(
    database="bw_basic", user="bw", password="fakey-fake", host="localhost", port=5432
)


class BaseModel(Model):
    class Meta:
        database = pg_db


class Subgraph(BaseModel):
    name = TextField()
    kind = TextField()
    modified = DateTimeField()

    @property
    def filepath_processed(self):
        return cache_dir / (safe_filename(self.name) + ".zip")

    @property
    def datapackage(self):
        return load_datapackage(ZipFS(str(self.filepath_processed)))

    def process_lci(self):
        if self.kind != "database":
            raise ValueError(
                "Processing to LCI datapackage only available for database subgraphs"
            )

        Flow = Node.alias()
        Activity = Node.alias()
        Product = Node.alias()

        biosphere = list(
            Edge.select(Edge.from_node_id, Edge.to_node_id, Edge.amount)
            .join(
                Flow, on=(Edge.from_node == Flow.id)
            )  # Assume biosphere always in one direction
            .switch(Edge)
            .join(Activity, on=(Edge.to_node == Activity.id))
            .where(
                Activity.subgraph_id == self.id,
                Flow.kind == "elementary",
                Activity.kind == "activity",
            )
            .tuples()
        )
        biosphere_indices = np.zeros(len(biosphere), dtype=INDICES_DTYPE)
        biosphere_indices["row"] = np.array([x[0] for x in biosphere])
        biosphere_indices["col"] = np.array([x[1] for x in biosphere])

        biosphere_data = np.array([x[2] for x in biosphere], dtype=float)

        technosphere_consumption = list(
            Edge.select(Edge.from_node_id, Edge.to_node_id, Edge.amount)
            .join(Product, on=(Edge.from_node == Product.id))
            .switch(Edge)
            .join(Activity, on=(Edge.to_node == Activity.id))
            .where(
                Activity.subgraph_id == self.id,
                Product.kind == "product",
                Activity.kind == "activity",
            )
            .tuples()
        )
        technosphere_production = list(
            Edge.select(Edge.to_node_id, Edge.from_node_id, Edge.amount)
            .join(Product, on=(Edge.to_node == Product.id))
            .switch(Edge)
            .join(Activity, on=(Edge.from_node == Activity.id))
            .where(
                Activity.subgraph_id == self.id,
                Product.kind == "product",
                Activity.kind == "activity",
            )
            .tuples()
        )
        tc, tp = len(technosphere_consumption), len(technosphere_production)

        technosphere_indices = np.zeros(tc + tp, dtype=INDICES_DTYPE)
        technosphere_indices["row"] = np.array(
            [x[0] for x in (technosphere_consumption + technosphere_production)]
        )
        technosphere_indices["col"] = np.array(
            [x[1] for x in (technosphere_consumption + technosphere_production)]
        )

        technosphere_data = np.array(
            [x[2] for x in (technosphere_consumption + technosphere_production)],
            dtype=float,
        )

        flip_array = np.zeros(tc + tp, dtype=bool)
        flip_array[:tc] = True

        dp = create_datapackage(
            fs=ZipFS(self.filepath_processed, write=True),
            name=clean_datapackage_name(self.name),
            sum_intra_duplicates=True,
            sum_inter_duplicates=False,
        )
        dp.add_persistent_vector(
            matrix="biosphere_matrix",
            name=clean_datapackage_name(self.name) + " biosphere",
            indices_array=biosphere_indices,
            data_array=biosphere_data,
        )
        dp.add_persistent_vector(
            matrix="technosphere_matrix",
            name=clean_datapackage_name(self.name) + " technosphere",
            indices_array=technosphere_indices,
            data_array=technosphere_data,
            flip_array=flip_array,
        )
        dp.finalize_serialization()

    def process_lcia(self):
        if self.kind != "impact category":
            raise ValueError(
                "Processing to LCIA datapackage only available for impact category subgraphs"
            )

        data = list(
            Edge.select(Edge.from_node, Edge.amount)
            .join(Node, on=(Edge.to_node_id == Node.id))
            .join(Subgraph, on=(Node.subgraph_id == Subgraph.id))
            .where(Subgraph.id == self.id)
            .tuples()
        )
        indices = np.zeros(len(data), dtype=INDICES_DTYPE)
        indices["row"] = np.array([x[0] for x in data])

        dp = create_datapackage(
            fs=ZipFS(self.filepath_processed, write=True),
            name=clean_datapackage_name(self.name),
            sum_intra_duplicates=True,
            sum_inter_duplicates=False,
        )
        dp.add_persistent_vector(
            matrix="characterization_matrix",
            name=clean_datapackage_name(self.name) + " characterization",
            indices_array=indices,
            data_array=np.array([x[1] for x in data], dtype=float),
            global_index=0,
        )
        dp.finalize_serialization()


class Node(BaseModel):
    name = TextField()
    kind = TextField()
    unit = TextField(null=True)
    location = TextField(null=True)
    subgraph = ForeignKeyField(Subgraph, backref="nodes")


class Edge(BaseModel):
    from_node = ForeignKeyField(Node, backref="edges_from")
    to_node = ForeignKeyField(Node, backref="edges_to")
    amount = FloatField()


pg_db.connect()
pg_db.create_tables([Subgraph, Node, Edge], safe=True)


def create_basic_data():
    try:
        Subgraph.get(Subgraph.id == 1)
        print("Base data already installed")
    except DoesNotExist:
        Subgraph.create(
            name="US EEIO 1.1", kind="database", modified=datetime.datetime.now()
        )
        gcc = Subgraph.create(
            name="Climate Change",
            kind="impact category",
            modified=datetime.datetime.now(),
        )
        Node.create(
            name="Climate Change", kind="midpoint", unit="kg CO2-eq.", subgraph=gcc
        )
