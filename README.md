# bw_simple_graph

This is a toy example of how one can use a custom backend with Brightway 2.5. The backend uses Postgres and a pure graph schema, with `Node` and `Edge` tables. It manually creates the datapackages to pass to `bw2calc`, and doesn't use `bw2data` at all. It is intended for people comfortable reading code, and is intended to serve as an example instead of being used directly as a normal library.

It is a toy example because `bw2io` is (usually) needed for data import, and `bw2io` relies heavily on `bw2data`. This dependency should be broken in Brightway 3, but this will be a serious development effort.

## Setup

Postgres must be installed with a suitable user role. Adjust the `PostgresqlDatabase` config as needed. I ran:

```sql
create user bw;
alter user bw with password 'fakey-fake';
create database bw_basic with owner bw template template1 encoding 'UTF-8';
```

Please take security seriously.

## Example data: US EEIO 1.1

When the connection to Postgres is working, you can run the function `create_basic_data`. This will create a subgraph for inventory data and a subgraph for a climate change method, as well as a `Node` for a climate change midpoint. This is just one modelling option, i don't claim it is the best, but it works.

You can then import the US EEIO data. There are ways to do this in Python, but it is also possible in the `psql` shell:

```sql
COPY node(id, name, kind, unit, location, subgraph_id)
    FROM '/path/to/nodes.csv'
    DELIMITER ','
    CSV HEADER;

COPY edge(from_node_id, to_node_id, amount)
    FROM '/path/to/edges.csv'
    DELIMITER ','
    CSV HEADER;

COPY edge(from_node_id, to_node_id, amount)
    FROM '/path/to/gcc.csv'
    DELIMITER ','
    CSV HEADER;
```

## Processing

`bw2calc` needs datapackages prepared by [`bw_processing`](https://github.com/brightway-lca/bw_processing). Processing is done by `Subgraph.process_lci` and `Subgraph.process_lcia`.

### Cache directory

Datapackages need to be stored somewhere. The default is in a directory specified by the environment variable `BW_SIMPLE_CACHE`.

## Example usage

```python
In [1]: from bw_simple_graph import Node as N, Edge as E, Subgraph as S

In [2]: something = N.get(N.kind == "activity")

In [3]: something.name, something.unit, something.location
Out[3]: ('Frozen food; at manufacturer', 'USD', 'United States')

In [4]: for edge in something.edges_from:
   ...:     print(edge.to_node.name, edge.to_node.kind)
Frozen food; at manufacturer product

In [5]: product = edge.to_node

In [6]: for edge in something.edges_to.limit(10).order_by(E.amount.desc()):
   ...:     print(edge.amount, edge.from_node.name)
0.1283574 Wholesale trade
0.0873663 Frozen food; at manufacturer
0.08081771 Fresh wheat, corn, rice, and other grains; at farm
0.06375308 Carbon dioxide
0.057288505 Cheese; at manufacturer
0.05538493 Fresh vegetables, melons, and potatoes; at farm
0.035845187 Packaged meat (except poultry); at manufacturer
0.034425475 Packaged poultry; at manufacturer
0.033406105 Company and enterprise management
0.02907457 Cardboard containers; at manufacturer

In [7]: S.get(S.name == "US EEIO 1.1").process_lci()

In [8]: S.get(S.name == "Climate Change").process_lcia()

In [9]: import bw2calc as bc

In [10]: lca = bc.LCA(
    ...:     demand={product.id: 1000},
    ...:     data_objs=[
    ...:         S.get(S.name == "US EEIO 1.1").datapackage,
    ...:         S.get(S.name == "Climate Change").datapackage
    ...:     ]
    ...: )

In [11]: lca.lci()

In [12]: lca.lcia()

In [13]: lca.score
Out[13]: 1013.0161025854002
```

## What's missing?

`bw2data` also provides:

* Automatic tracking of modifications, so datapackages are automatically regenerated when needed
* A flexible database schema where you can add arbitrary attributes (through the use of a serialized pickle column)
* Separate LCIA normalization and weighting (though they do not appear to be used much)
* A search index and search functionality
* Utilities for testing on temporary databases
