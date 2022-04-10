import copy
import datetime
from decimal import Decimal
import functools as ft
import library
EDATE=datetime.datetime.fromisoformat('2021-06-30').date()
LAST_ALLOWANCE_DATE=datetime.datetime.fromisoformat('2016-06-30').date()
LARGE_HAIRCUT_RATE=0.05
LARGE_ALLOWANCE_RATE=0.05
LARGE_PLEDGE_MINIMUM=10_000
ONE=Decimal(1)
ZERO=Decimal()
#note: the query must sort each pledge by account number

class PledgeLoad:
    date_thresholds=[EDATE+datetime.timedelta(days=365),EDATE+datetime.timedelta(days=365*5)]
    date_cols=['lessthanoneyear','onetofiveyears','greaterthanfiveyears']
    def __init__(self,discount_rates):
        self.null=True 
        self.main={} #first columns on left output
        self.gl_totals={} #holds totals that aren't going to be displayed
        self.payments={} #most just detail for computation
        self.columns={} #the repeated tuples to the right
        self.reconciliation={}
        self.errors=set() #just validation stuff
        self.discount_rates=discount_rates
        self.discount_rate=None
        self.daily_rate=None
        #
        self.columns['gross_receipts']={'lessthanoneyear':Decimal(),'onetofiveyears':Decimal(),'greaterthanfiveyears':Decimal()}
        self.columns['haircuts']={'lessthanoneyear':Decimal(),'onetofiveyears':Decimal(),'greaterthanfiveyears':Decimal()}
        self.columns['allowances']={'lessthanoneyear':Decimal(),'onetofiveyears':Decimal(),'greaterthanfiveyears':Decimal()}
        self.columns['net_of_haircuts_and_allowances']={'lessthanoneyear':Decimal(),'onetofiveyears':Decimal(),'greaterthanfiveyears':Decimal()}
        self.columns['discounts']={'lessthanoneyear':Decimal(),'onetofiveyears':Decimal(),'greaterthanfiveyears':Decimal()}
        self.columns['net']={'lessthanoneyear':Decimal(),'onetofiveyears':Decimal(),'greaterthanfiveyears':Decimal()}
        #
        self.payment_proto={'days':0,'daily_rate':0.0,
                            'payment_amount':Decimal(),'gross_receipts':Decimal(),'haircuts':Decimal(),'net_of_haircuts':Decimal(),
                            'allowances':Decimal(),'discounts':Decimal(),'net':Decimal()}
    def intake(self,adict):
        '''each query row is passed in here and split into 3 pieces'''
##        print(adict)
        adict=self.translate_grant_pledges(adict)
        self.load_main_dict(adict)
        self.load_payments(adict)
        self.load_gl_totals(adict)
    def translate_grant_pledges(self,adict):
        if adict['pledge_type']=='GD':
            adict['allocation_code']='6716%s'%adict['allocation_code'][-5:] #4744.12.1->6716.12.1
        return adict
    def load_main_dict(self,adict):
        acct=adict['account_number']
        if acct.startswith('12000') and self.null:
            self.null=False
            for k in ['pledge_number','fund','dept','deptname','bbfe',
                      'allocation_code','donor_id',
                      'pledge_amount','pledge_amount_paid',
                      'pledge_type','date_of_record']:
                if not k in self.main:
                    self.main[k]=adict[k]
                else:
                    if self.main[k]!=adict[k]:
                        e='pledge %s attempting to overwrite %s=%s with %s'%(self.main['pledge_number'],k,self.main[k],adict[k])
                        self.errors.add(e)
    def load_payments(self,adict):
        acct=adict['account_number']
        if acct.startswith('12000'):
            pd=adict['payment_date']
            key=pd,self.assign_date_col(pd) #(date,'lessthanoneyear')
            if not key in self.payments:
                self.payments[key]=copy.deepcopy(self.payment_proto)
                self.payments[key]['payment_date']=pd
                self.payments[key]['payment_amount']=adict['payment_amount']
            else:
                self.payments[key]['payment_amount']+=adict['payment_amount']
    def load_gl_totals(self,adict):
        acct=adict['account_number']
        if not acct in self.gl_totals: self.gl_totals[acct]=adict['bbfe']
    def assign_date_col(self,date):
        if date<self.date_thresholds[0]:
            return 'lessthanoneyear'
        elif date<=self.date_thresholds[1]:
            return 'onetofiveyears'
        else:
            return 'greaterthanfiveyears'
 

        

class PledgeProcess(PledgeLoad):
    def __init__(self,discount_rates):
        super().__init__(discount_rates)
    def process(self):
        '''this performs the computations and validations'''
        self.get_discount_rate()
        self.main['pledge_balance']=self.main['pledge_amount']-self.main['pledge_amount_paid']
        self.main['total_payments']=ft.reduce(lambda a,b: a+b['payment_amount'],self.payments.values(),Decimal())
        self.compute_payments_dict()
        self.post_payments_dict()
        self.validate()
    def get_discount_rate(self):
        year=self.main['date_of_record'].year
        month=self.main['date_of_record'].month
        try:
            self.discount_rate=self.discount_rates[(year,month)]
        except:
            e='pledge %s discount rate lookup failed for year=%s and month=%s. Setting discount rate to 1.0'%(self.main['pledge_number'],year,month)
            self.errors.add(e)
            self.discount_rate=1.0
        self.daily_rate=round(self.discount_rate/365,10)
##        print(self.discount_rate,self.daily_rate)
    def compute_payments_dict(self):
        for k,py in self.payments.items():
            phrase=k[1]
            py['days']=(py['payment_date']-EDATE).days
            py['gross_receipts']=py['payment_amount']
            if self.main['date_of_record']>LAST_ALLOWANCE_DATE:
                py['haircuts']=round(py['payment_amount']*Decimal(LARGE_HAIRCUT_RATE),2)
            if self.main['date_of_record']<=LAST_ALLOWANCE_DATE:
                py['allowances']=round(py['gross_receipts']*Decimal(LARGE_ALLOWANCE_RATE),2)
            py['net_of_haircuts_and_allowances']=py['gross_receipts']-py['haircuts']-py['allowances']
            if not phrase=='lessthanoneyear':
                denominator=self.discount_factor(self.daily_rate,py['days'])
##                print(denominator)
                amt=float(py['net_of_haircuts_and_allowances'])
                pv=round(amt/denominator,2)
                py['discounts']=round(amt-pv,2)
                py['discounts']=Decimal(py['discounts'])
##            print('discounts',py['discounts'])
            py['net']=py['net_of_haircuts_and_allowances']-py['discounts']
##            print('net',py['net'])
    def discount_factor(self,rdivn,t):
        if t<0:
            return 1.0
        else:
            return float((1+rdivn)**(t))
    def post_payments_dict(self):
        for k,py in self.payments.items():
            phrase=k[1]
            for col in ['gross_receipts','haircuts','allowances','net_of_haircuts_and_allowances','discounts','net']:
                self.columns[col][phrase]+=py[col]
    def validate(self):
        '''all the validations go here'''
        test=self.main['pledge_balance']-self.main['total_payments']
        if test!=ZERO:
            e='pledge %s payments=%s does not equal balance=%s'%(self.main['pledge_number'],self.main['total_payments'],self.main['pledge_balance'])
            self.errors.add(e)
        #
        if self.main['fund']!=self.main['allocation_code'][:4]:
            e='pledge %s fund=%s does not equate to allocation_code=%s'%(self.main['pledge_number'],self.main['fund'],self.main['allocation_code'])
            self.errors.add(e)
        #
        if self.main['pledge_amount']<Decimal(LARGE_PLEDGE_MINIMUM):
            e='pledge %s initial balance=%s.  This looks like a small pledge.'%(self.main['pledge_number'],self.main['pledge_amount'])
            self.errors.add(e)


class PledgeExcel(PledgeProcess):
    def __init__(self,discount_rates):
        super().__init__(discount_rates)
    def errors_to_excel(self):
        if not self.errors:
            return None
        else:
            errors=[e for e in self.errors]
            return errors
    def summary_to_excel(self):
        summary=[]
        summary+=[self.main['pledge_number'],self.main['fund'],self.main['donor_id']]
        summary+=[self.main['date_of_record'],self.main['pledge_amount'],self.main['pledge_balance']]
        for col in ['gross_receipts','haircuts','allowances','net_of_haircuts_and_allowances','discounts','net']:
            dc=self.date_cols
            summary+=[self.columns[col][dc[0]],self.columns[col][dc[1]],self.columns[col][dc[2]]]
##        print(summary)
        return summary
    def reconciliation_to_excel(self):
        proto={'pledge_number':self.main['pledge_number'],'fund':self.main['fund'],'account':'','advance':Decimal(),'bbfe':Decimal(),'diff':Decimal()}
        adict={}
        for acct,total in self.gl_totals.items():
            k=acct
            if not acct in adict:
                adict[k]=copy.deepcopy(proto)
                adict[k]['account']=acct
            adict[k]['bbfe']+=total
            adict[k]['diff']-=total
        #
        ending=self.main['allocation_code'][-5:-1]+'0'
##        grt=self.columns['gross_receipts']={'lessthanoneyear':Decimal(),'onetofiveyears':Decimal(),'greaterthanfiveyears':Decimal()}
        grt=ft.reduce(lambda a,b: a+b,self.columns['gross_receipts'].values(),Decimal())
        self.post_advance(adict,'12000',ending,proto,grt)
        grt=ft.reduce(lambda a,b: a+b,self.columns['haircuts'].values(),Decimal())
        self.post_advance(adict,'12001',ending,proto,-grt)
        grt=ft.reduce(lambda a,b: a+b,self.columns['allowances'].values(),Decimal())
        self.post_advance(adict,'12030',ending,proto,-grt)
        grt=ft.reduce(lambda a,b: a+b,self.columns['discounts'].values(),Decimal())
        self.post_advance(adict,'12040',ending,proto,-grt)
        #
        alist=[]
        for k,v in adict.items():
            tmp=[]
            for k2,v2 in v.items():
                tmp+=[v2]
            alist+=[tmp]
##        print(alist)
        return alist

    def post_advance(self,adict,acct,ending,proto,amt):
        if amt==ZERO:return
        k='%s%s'%(acct,ending)
        if k in adict:
            adict[k]['advance']+=amt
            adict[k]['diff']+=amt
        else:
##            print('reconciliation to excel: trouble posting advance to acct=%s, allocation_code=%s'%(k,self.main['allocation_code']))
            adict[k]=copy.deepcopy(proto)
            adict[k]['account']=k
            adict[k]['advance']+=amt
            adict[k]['diff']+=amt

    def je_to_excel(self):
        t={'12001':['valuation','42400'],
           '12030':['allowance','42407'],
           '12040':['discount','42408'],
           }
        ending=self.main['allocation_code'][-5:]
        pledgeno=self.main['pledge_number']
        recon=self.reconciliation_to_excel()
        alist=[]
        for r in recon:
            pno,fd,acctno,_,_,diff=r
            if diff==ZERO or (-0.1<diff<0.1) or acctno.startswith('12000'): continue
            acctnostart=acctno[:5]
            tmp=[fd,acctno,EDATE,'large pledge %s adj.'%t[acctnostart][0],diff,'','Standard','R','Pledge Number',pledgeno]
            alist+=[tmp]
            tmp=[fd,'%s%s'%(t[acctnostart][1],ending),EDATE,'large pledge %s adj.'%t[acctnostart][0],-diff,'','Standard','R','Pledge Number',pledgeno]
            alist+=[tmp]
        return alist
        
        
            
        
