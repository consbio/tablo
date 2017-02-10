-- Point dataset
CREATE SEQUENCE db_point_test_id_seq
  INCREMENT 1
  MINVALUE 1
  MAXVALUE 9223372036854775807
  START 24
  CACHE 1;

CREATE TABLE db_point_test
(
  db_id integer NOT NULL DEFAULT nextval('db_point_test_id_seq'::regclass),
  prop1 integer NOT NULL,
  prop2 integer,
  db_creator text NOT NULL,
  db_created_date timestamp without time zone NOT NULL,
  dbasin_geom geometry(Geometry, 3857),
  CONSTRAINT db_point_test_pkey PRIMARY KEY (db_id)
);

-- Inserts 10 random points in db_point_test
DO $$ BEGIN
  FOR i IN 1..10 LOOP
    INSERT INTO db_point_test
    VALUES (i, random() * 10, random() * 10, 'user1', current_timestamp,
            ST_Transform(ST_SetSrid(ST_MakePoint((random() - 0.5) * 360, (random() - 0.5) * 180), 4326), 3857));
  END LOOP;
END $$;

-- Polyline dataset
CREATE SEQUENCE db_polyline_test_id_seq
  INCREMENT 1
  MINVALUE 1
  MAXVALUE 9223372036854775807
  START 24
  CACHE 1;

CREATE TABLE db_polyline_test
(
  db_id integer NOT NULL DEFAULT nextval('db_polyline_test_id_seq'::regclass),
  prop1 integer NOT NULL,
  prop2 integer,
  db_creator text NOT NULL,
  db_created_date timestamp without time zone NOT NULL,
  dbasin_geom geometry(Geometry, 3857),
  CONSTRAINT db_polyline_test_pkey PRIMARY KEY (db_id)
);

-- Inserts 10 random polylines in db_polyline_test
DO $$ BEGIN
  FOR i IN 1..10 LOOP
    INSERT INTO db_polyline_test
    VALUES (i, random() * 10, random() * 10, 'user1', current_timestamp,
            ST_Transform(
                ST_SetSrid(ST_MakeLine(
                    ARRAY[
                        ST_MakePoint((random() - 0.5) * 360, (random() - 0.5) * 180),
                        ST_MakePoint((random() - 0.5) * 360, (random() - 0.5) * 180),
                        ST_MakePoint((random() - 0.5) * 360, (random() - 0.5) * 180),
                        ST_MakePoint((random() - 0.5) * 360, (random() - 0.5) * 180)]
                ), 4326), 3857));
  END LOOP;
END $$;

-- Multiline polyline table
CREATE SEQUENCE db_multi_polyline_test_id_seq
  INCREMENT 1
  MINVALUE 1
  MAXVALUE 9223372036854775807
  START 24
  CACHE 1;

CREATE TABLE db_multi_polyline_test
(
  db_id integer NOT NULL DEFAULT nextval('db_multi_polyline_test_id_seq'::regclass),
  prop1 integer NOT NULL,
  prop2 integer,
  db_creator text NOT NULL,
  db_created_date timestamp without time zone NOT NULL,
  dbasin_geom geometry(Geometry, 3857),
  CONSTRAINT db_multi_polyline_test_pkey PRIMARY KEY (db_id)
);

-- Inserts 10 random polylines in db_multi_polyline_test
DO $$ BEGIN
  FOR i IN 1..10 LOOP
    INSERT INTO db_multi_polyline_test
    VALUES (i, random() * 10, random() * 10, 'user1', current_timestamp,
            ST_Transform(
                ST_SetSrid(ST_MULTI(ST_MakeLine(
                    ARRAY[
                        ST_MakePoint((random() - 0.5) * 360, (random() - 0.5) * 180),
                        ST_MakePoint((random() - 0.5) * 360, (random() - 0.5) * 180),
                        ST_MakePoint((random() - 0.5) * 360, (random() - 0.5) * 180),
                        ST_MakePoint((random() - 0.5) * 360, (random() - 0.5) * 180)]
                )), 4326), 3857));
  END LOOP;
END $$;

-- Polygon dataset
CREATE SEQUENCE db_polygon_test_id_seq
  INCREMENT 1
  MINVALUE 1
  MAXVALUE 9223372036854775807
  START 24
  CACHE 1;

CREATE TABLE db_polygon_test
(
  db_id integer NOT NULL DEFAULT nextval('db_polygon_test_id_seq'::regclass),
  prop1 integer NOT NULL,
  prop2 integer,
  db_creator text NOT NULL,
  db_created_date timestamp without time zone NOT NULL,
  dbasin_geom geometry(Geometry, 3857),
  CONSTRAINT db_polygon_test_pkey PRIMARY KEY (db_id)
);

-- Inserts 10 random polygons in db_polygon_test
INSERT INTO db_polygon_test
SELECT db_id, random(), random(), db_creator, current_timestamp, ST_MakePolygon(ST_AddPoint(dbasin_geom, ST_StartPoint(dbasin_geom))) FROM db_polyline_test;


-- Multi polygon table
CREATE SEQUENCE db_multi_polygon_test_id_seq
  INCREMENT 1
  MINVALUE 1
  MAXVALUE 9223372036854775807
  START 24
  CACHE 1;

CREATE TABLE db_multi_polygon_test
(
  db_id integer NOT NULL DEFAULT nextval('db_multi_polygon_test_id_seq'::regclass),
  prop1 integer NOT NULL,
  prop2 integer,
  db_creator text NOT NULL,
  db_created_date timestamp without time zone NOT NULL,
  dbasin_geom geometry(Geometry, 3857),
  CONSTRAINT db_multi_polygon_test_pkey PRIMARY KEY (db_id)
);

 -- Inserts 10 random multipolygons in db_polygon_test
INSERT INTO db_multi_polygon_test
SELECT db_id, random(), random(), db_creator, current_timestamp, ST_MULTI(ST_MakePolygon(ST_AddPoint(dbasin_geom, ST_StartPoint(dbasin_geom)))) FROM db_polyline_test;


