import { ComponentFixture, TestBed } from '@angular/core/testing';
import { RouterTestingModule } from '@angular/router/testing';
import { By } from '@angular/platform-browser';
import { RouterLinkActive } from '@angular/router';

import { SidebarComponent } from './sidebar.comonent';

describe('SidebarComponent', () => {
  let component: SidebarComponent;
  let fixture: ComponentFixture<SidebarComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      // SidebarComponent is standalone, so we import it directly.
      // RouterTestingModule is needed to handle routerLink and routerLinkActive.
      imports: [SidebarComponent, RouterTestingModule.withRoutes([])],
    }).compileComponents();

    fixture = TestBed.createComponent(SidebarComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create the component', () => {
    expect(component).toBeTruthy();
  });

  it('should initialize with a list of 6 navigation links', () => {
    expect(component.navLinks).toBeDefined();
    expect(component.navLinks.length).toBe(6);
    expect(component.navLinks[0].label).toBe('Dashboard');
    expect(component.navLinks[5].label).toBe('Settings');
  });

  it('should render a navigation link for each item in navLinks', () => {
    const linkDebugElements = fixture.debugElement.queryAll(By.css('a'));
    expect(linkDebugElements.length).toBe(component.navLinks.length);
  });

  it('should render the correct labels for each navigation link', () => {
    const linkElements: HTMLElement[] = fixture.nativeElement.querySelectorAll('a');

    component.navLinks.forEach((navLink, index) => {
      const labelElement = linkElements[index].querySelector('.ml-3');
      expect(labelElement).withContext(`Label for ${navLink.label} not found`).toBeTruthy();
      expect(labelElement?.textContent?.trim()).withContext(`Label for ${navLink.label} is incorrect`).toBe(navLink.label);
    });
  });

  it('should render the correct paths (href) for each navigation link', () => {
    const linkDebugElements = fixture.debugElement.queryAll(By.css('a'));

    component.navLinks.forEach((navLink, index) => {
      // The href attribute on the anchor tag will be correctly resolved by RouterTestingModule
      expect(linkDebugElements[index].properties['href']).toBe(navLink.path);
    });
  });

  it('should render an SVG icon for each navigation link', () => {
    const linkElements: HTMLElement[] = fixture.nativeElement.querySelectorAll('a');

    component.navLinks.forEach((navLink, index) => {
      const svgElement = linkElements[index].querySelector('svg');
      const pathElement = svgElement?.querySelector('path');

      expect(svgElement).withContext(`SVG for ${navLink.label} not found`).toBeTruthy();
      expect(pathElement).withContext(`SVG path for ${navLink.label} not found`).toBeTruthy();
      expect(pathElement?.getAttribute('d')).withContext(`SVG path for ${navLink.label} is incorrect`).toBe(navLink.iconSvgPath);
    });
  });

  it('should apply routerLinkActiveOptions with exact: true for the dashboard link', () => {
    const dashboardLinkDe = fixture.debugElement.query(By.css('a[href="/dashboard"]'));
    const rlaInstance = dashboardLinkDe.injector.get(RouterLinkActive);
    expect(rlaInstance.routerLinkActiveOptions).toEqual({ exact: true });
  });

  it('should apply routerLinkActiveOptions with exact: false for links without exactMatch property', () => {
    const positionsLinkDe = fixture.debugElement.query(By.css('a[href="/dashboard/positions"]'));
    const rlaInstance = positionsLinkDe.injector.get(RouterLinkActive);
    expect(rlaInstance.routerLinkActiveOptions).toEqual({ exact: false });
  });
});
