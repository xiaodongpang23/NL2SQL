-- Create tables
CREATE TABLE accounts (
    id integer ,
    account_id integer PRIMARY KEY,
    customer_id integer,
    account_type character varying(256),
    opening_date date,
    balance bigint,
    currency character varying(256)
);

CREATE TABLE customer (
    id integer,
    customer_id integer PRIMARY KEY ,
    name character varying(256) ,
    age integer,
    gender character varying(256) ,
    address character varying(256) ,
    phone character varying(256) ,
    email character varying(256)
);

CREATE TABLE investments (
    id integer ,
    investment_id integer PRIMARY KEY,
    customer_id integer ,
    investment_type character varying(256) ,
    investment_name character varying(256) ,
    purchase_date date ,
    purchase_price bigint ,
    quantity integer 
);


CREATE TABLE loans (
    id integer ,
    loan_id integer PRIMARY KEY,
    customer_id integer ,
    loan_type character varying(256) ,
    loan_amount bigint ,
    interest_rate integer ,
    start_date date ,
    end_date date 
);

CREATE TABLE orders (
    id integer ,
    order_id integer PRIMARY KEY,
    customer_id integer ,
    order_type character varying(256) ,
    order_date date ,
    investment_id integer ,
    quantity integer ,
    price integer 
);

CREATE TABLE transactions (
    id integer ,
    transaction_id integer PRIMARY KEY ,
    account_id integer REFERENCES accounts(account_id),
    transaction_type character varying(256) ,
    transaction_date date ,
    amount integer ,
    description character varying(256) 
);