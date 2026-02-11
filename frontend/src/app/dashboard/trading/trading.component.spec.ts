import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { TradingComponent } from './trading.component';
import { ActivatedRoute, Params } from '@angular/router';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { AuthService } from '../../auth.service';
import { BehaviorSubject } from 'rxjs';
import { FormsModule } from '@angular/forms';
import { CommonModule } from '@angular/common';

describe('TradingComponent', () => {
  let component: TradingComponent;
  let fixture: ComponentFixture<TradingComponent>;
  let httpTestingController: HttpTestingController;
  let authService: jasmine.SpyObj<AuthService>;
  
  // Use BehaviorSubject to control route params dynamically
  let queryParamsSubject: BehaviorSubject<Params>;

  const apiUrl= 'https://auth.ticker-stream.com/api';

  beforeEach(async () => {
    // 1. Initialize the subject with empty params
    queryParamsSubject = new BehaviorSubject<Params>({});
    const authServiceSpy = jasmine.createSpyObj('AuthService', ['currentUserId']);

    await TestBed.configureTestingModule({
      imports: [
        CommonModule,
        FormsModule,
        HttpClientTestingModule,
        TradingComponent 
      ],
      providers: [
        { provide: AuthService, useValue: authServiceSpy },
        {
          provide: ActivatedRoute,
          useValue: {
            // Return the subject as an observable so the component can subscribe
            queryParams: queryParamsSubject.asObservable(),
          },
        },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(TradingComponent);
    component = fixture.componentInstance;
    httpTestingController = TestBed.inject(HttpTestingController);
    authService = TestBed.inject(AuthService) as jasmine.SpyObj<AuthService>;

    // IMPORTANT: Do NOT call fixture.detectChanges() here.
    // We need to spy on methods BEFORE ngOnInit runs.
  });

  afterEach(() => {
    httpTestingController.verify();
  });

  it('should create', () => {
    fixture.detectChanges(); // Trigger init now
    expect(component).toBeTruthy();
  });

  describe('ngOnInit', () => {
    it('should set ticker from query params and fetch current price', () => {
      // 1. Spy BEFORE ngOnInit runs
      spyOn(component, 'fetchCurrentPrice');

      // 2. Set the route params BEFORE ngOnInit runs
      queryParamsSubject.next({ ticker: 'AAPL' });

      // 3. Trigger ngOnInit
      fixture.detectChanges();

      // 4. Assert
      expect(component.ticker()).toBe('AAPL');
      expect(component.fetchCurrentPrice).toHaveBeenCalled();
    });

    it('should not fetch current price if no ticker in query params', () => {
      spyOn(component, 'fetchCurrentPrice');
      
      // Emit empty params
      queryParamsSubject.next({});
      
      fixture.detectChanges();

      expect(component.ticker()).toBe('');
      expect(component.fetchCurrentPrice).not.toHaveBeenCalled();
    });
  });

  describe('fetchCurrentPrice', () => {
    // We need to initialize the component before testing methods
    beforeEach(() => {
        fixture.detectChanges(); 
    });

    it('should fetch and set current price for a valid ticker', () => {
      component.ticker.set('MSFT');
      component.fetchCurrentPrice();

      const req = httpTestingController.expectOne(`${apiUrl}/stock/MSFT`);
      expect(req.request.method).toEqual('GET');
      req.flush({ latestPrice: 150.50 });

      expect(component.currentPrice()).toBe(150.50);
      expect(component.errorMessage()).toBeNull();
    });

    it('should handle error when fetching current price', fakeAsync(() => {
      component.ticker.set('INVALID');
      component.fetchCurrentPrice();

      const req = httpTestingController.expectOne(`${apiUrl}/stock/INVALID`);
      expect(req.request.method).toEqual('GET');
      req.error(new ErrorEvent('Network error'));

      expect(component.currentPrice()).toBe(0);
      expect(component.errorMessage()).toContain('Error fetching price for INVALID.');
      
      // Test the timeout clearing
      tick(4000);
      expect(component.errorMessage()).toBeNull();
    }));

    it('should set current price to 0 and show error if latestPrice is undefined', fakeAsync(() => {
      component.ticker.set('NO_PRICE');
      component.fetchCurrentPrice();

      const req = httpTestingController.expectOne(`${apiUrl}/stock/NO_PRICE`);
      expect(req.request.method).toEqual('GET');
      req.flush({}); 

      expect(component.currentPrice()).toBe(0);
      expect(component.errorMessage()).toContain('Could not fetch current price for NO_PRICE.');
      
      // Test the timeout clearing
      tick(4000);
      expect(component.errorMessage()).toBeNull();
    }));

    it('should not make a request if ticker is empty', () => {
      component.ticker.set('');
      component.fetchCurrentPrice();
      httpTestingController.expectNone(`${apiUrl}/stock/`);
      expect(component.currentPrice()).toBe(0); 
    });
  });

  describe('submitTrade', () => {
    beforeEach(() => {
      // Initialize component
      fixture.detectChanges(); 
      
      // Setup default valid state
      authService.currentUserId.and.returnValue('123');
      component.ticker.set('GOOG');
      component.quantity.set(10);
      component.currentPrice.set(100); 
      component.orderType.set('MARKET');
      component.tradeAction.set('BUY');
    });

    it('should show error if ticker is empty', () => {
      component.ticker.set('');
      component.submitTrade();
      expect(component.errorMessage()).toBe('Please enter a ticker symbol.');
      expect(component.isSubmitting()).toBeFalse();
    });

    it('should show error if quantity is invalid', () => {
      component.quantity.set(0);
      component.submitTrade();
      expect(component.errorMessage()).toBe('Please enter a valid quantity.');
      expect(component.isSubmitting()).toBeFalse();
    });

    it('should show error if limit price is invalid for LIMIT order', () => {
      component.orderType.set('LIMIT');
      component.limitPrice.set(0);
      component.submitTrade();
      expect(component.errorMessage()).toBe('Please enter a valid limit price for a limit order.');
      expect(component.isSubmitting()).toBeFalse();
    });

    it('should show error if current market price is unavailable for MARKET order', () => {
      component.orderType.set('MARKET');
      component.currentPrice.set(0);
      component.submitTrade();
      expect(component.errorMessage()).toBe('Current market price is unavailable. Cannot place market order.');
      expect(component.isSubmitting()).toBeFalse();
    });

    it('should show error if user is not logged in', () => {
      authService.currentUserId.and.returnValue(null);
      component.submitTrade();
      expect(component.errorMessage()).toBe('User not logged in. Cannot place trade.');
      expect(component.isSubmitting()).toBeFalse();
    });

    it('should submit a MARKET BUY trade successfully', fakeAsync(() => {
      component.submitTrade();

      const req = httpTestingController.expectOne(`${apiUrl}/trade/`);
      expect(req.request.method).toEqual('POST');
      expect(req.request.body).toEqual({
        user_id: 123, 
        ticker: 'GOOG',
        action: 'BUY',
        quantity: 10,
        price: 100,
        is_bot_trade: false,
        order_type: 'MARKET',
        limit_price: null,
      });
      req.flush({ message: 'Trade placed successfully!' });

      expect(component.isSubmitting()).toBeFalse();
      expect(component.successMessage()).toBe('Trade placed successfully!');
      expect(component.ticker()).toBe('');
      expect(component.quantity()).toBeNull();
      expect(component.currentPrice()).toBe(0);

      // Test timeout
      tick(4000);
      expect(component.successMessage()).toBeNull();
    }));

    it('should submit a LIMIT SELL trade successfully', () => {
      component.tradeAction.set('SELL');
      component.orderType.set('LIMIT');
      component.limitPrice.set(105);
      component.submitTrade();

      const req = httpTestingController.expectOne(`${apiUrl}/trade/`);
      expect(req.request.method).toEqual('POST');
      expect(req.request.body).toEqual({
        user_id: 123,
        ticker: 'GOOG',
        action: 'SELL',
        quantity: 10,
        price: 105, // For Limit orders, logic uses limit price
        is_bot_trade: false,
        order_type: 'LIMIT',
        limit_price: 105,
      });
      req.flush({ message: 'Sell order placed!' });

      expect(component.isSubmitting()).toBeFalse();
      expect(component.successMessage()).toBe('Sell order placed!');
      expect(component.ticker()).toBe('');
      expect(component.quantity()).toBeNull();
      expect(component.limitPrice()).toBeNull();
    });

    it('should handle trade submission error', fakeAsync(() => {
      component.submitTrade();

      const req = httpTestingController.expectOne(`${apiUrl}/trade/`);
      expect(req.request.method).toEqual('POST');
      req.error(new ErrorEvent('Server error', { message: 'Failed to process trade' }), { status: 500, statusText: 'Server Error' });

      expect(component.isSubmitting()).toBeFalse();
      expect(component.errorMessage()).toBe('Trade submission failed. Please try again.');
      expect(component.successMessage()).toBeNull();

      tick(4000);
      expect(component.errorMessage()).toBeNull();
    }));
  });
});