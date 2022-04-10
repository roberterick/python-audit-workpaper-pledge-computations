import datetime
import decimal
import urllib
import sqlalchemy as sa

class Library:
    def download(self,sql):
        exact='DRIVER={SQL Server Native Client 11.0};SERVER=abidb;Trusted_Connection=yes;'
        params = urllib.parse.quote(exact)
        engine = sa.create_engine("mssql+pyodbc:///?odbc_connect=%s"%params)
##
        ll=[]
        with engine.connect() as conn:
            for row in conn.execute(sql):
                ll+=[list(row)]
        return ll

    def sql_discount_rates(self):
        return '''
        select *
        from uo_pledge_discount_rate uadr
        ;
        '''
    
    def sql_full(self,edate):
        return '''
        declare @edate date = '{edate}';
        declare @keepstatic date = '2015-06-30';

        with cte01 as(
        select
        trx.xsrc_pledge_num pledge_number
        ,trx.account_number
        ,trx.fund_number
        ,fund.department_code
        ,fund.department
        ,sum(trx.amount) amount
        from
        uo_fund fund
        join uo_gl_transaction trx on fund.fund_id=trx.fund_id
        join acctetl.dbo.uo_batch batch on batch.batch_id=trx.batch_id
        where
        left(trx.account_number,5) in ('12000','12001','12030','12040')
        and trx.post_date between @keepstatic and @edate
        and trx.post_status='Posted'
        and trx.fund_number not in ('7000')
        and trx.xsrc_pledge_num is not null
        group by
        trx.xsrc_pledge_num
        ,trx.account_number
        ,trx.fund_number
        ,fund.department_code
        ,fund.department
        having sum(trx.amount)<>0
        --order by 1,2,3
        )

        ,ctepmt as(
        select
        ug.allocation_code
        ,ug.pledge_number
        ,ug.donor_id
        ,ug.pledge_type
        ,ug.pledge_amount
        ,ug.pledge_amount_paid
        ,convert(date, ug.date_of_record,112) date_of_record
        ,upps.payment_date
        ,upps.payment_amount
        from uo_gift ug
        join uo_pledge_payment_schedule upps ON upps.pledge_number=ug.txn_number
        and upps.payment_status_code='U'
        where
        ug.legal_amount>0
        and ug.pledge_type in ('GD','FP') --is PF missing from the pledge recon?  Are PFs transmitting to BBFE?
        --and ug.pledge_status='A'
        --and ug.txn_source='P'
        )

        select
        *
        from cte01 c
        join ctepmt on ctepmt.pledge_number=c.pledge_number
        --where c.fund_number in ('1082')
        order by 1,2,3
        ;
        '''.format(edate=edate)

    def sql_truncated(self,edate):
        return '''
        declare @edate date = '{edate}';
        declare @keepstatic date = '2015-06-30';

        with cte01 as(
        select
        trx.xsrc_pledge_num pledge_number
        ,trx.account_number
        ,trx.fund_number
        ,fund.department_code
        ,fund.department
        ,sum(trx.amount) amount
        from
        uo_fund fund
        join uo_gl_transaction trx on fund.fund_id=trx.fund_id
        join acctetl.dbo.uo_batch batch on batch.batch_id=trx.batch_id
        where
        left(trx.account_number,5) in ('12000','12001','12030','12040')
        and trx.post_date between @keepstatic and @edate
        and trx.post_status='Posted'
        and trx.fund_number not in ('7000')
        and trx.xsrc_pledge_num is not null
        group by
        trx.xsrc_pledge_num
        ,trx.account_number
        ,trx.fund_number
        ,fund.department_code
        ,fund.department
        having sum(trx.amount)<>0
        --order by 1,2,3
        )

        ,ctepmt as(
        select
        ug.allocation_code
        ,ug.pledge_number
        ,ug.donor_id
        ,ug.pledge_type
        ,ug.pledge_amount
        ,ug.pledge_amount_paid
        ,convert(date, ug.date_of_record,112) date_of_record
        ,upps.payment_date
        ,upps.payment_amount
        from uo_gift ug
        join uo_pledge_payment_schedule upps ON upps.pledge_number=ug.txn_number
        and upps.payment_status_code='U'
        where
        ug.legal_amount>0
        and ug.pledge_type in ('GD','FP') --is PF missing from the pledge recon?  Are PFs transmitting to BBFE?
        --and ug.pledge_status='A'
        --and ug.txn_source='P'
        )

        select top(1000)
        *
        from cte01 c
        join ctepmt on ctepmt.pledge_number=c.pledge_number
        order by 1,2,3
        ;
        '''.format(edate=edate)
