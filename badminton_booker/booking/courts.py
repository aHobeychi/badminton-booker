#!/usr/bin/env python3
"""Badminton court booking and availability checking module."""

import json
import os
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
from dotenv import load_dotenv
from badminton_booker.booking.handle_time import generate_time_object

# Load environment variables from .env file if it exists
load_dotenv()

def generate_selected_date() -> list[str]:
    """Selected date will be the next 4 days from today as a list of strings using a two digit format."""
    today = datetime.now()
    selected_dates = []
    for i in range(4):
        date = today + timedelta(days=i)
        selected_dates.append(date.strftime("%d"))
    return selected_dates

async def select_time_on_page(page): 
    """Select time for booking."""
    # Start time
    await page.locator('#u6510_edFacilityReservationSearchStartTime').get_by_role('textbox', name='HH').click()
    await page.locator('#u6510_edFacilityReservationSearchStartTime').get_by_role('textbox', name='HH').fill('18')
    await page.locator('#u6510_edFacilityReservationSearchStartTime').get_by_role('textbox', name='MM').click()
    await page.locator('#u6510_edFacilityReservationSearchStartTime').get_by_role('textbox', name='MM').fill('00')
    
    # Finish Time
    await page.locator('#u6510_edFacilityReservationSearchEndTime').get_by_role('textbox', name='HH').click()
    await page.locator('#u6510_edFacilityReservationSearchEndTime').get_by_role('textbox', name='HH').fill('22')
    await page.locator('#u6510_edFacilityReservationSearchEndTime').get_by_role('textbox', name='HH').press('Enter')

async def generate_available_booking_list(reservation_elements):
    """Generate a list of available bookings from reservation elements."""
    reservations = []
    print(f'Found {len(reservation_elements)} reservation elements')
    
    for element in reservation_elements:
        # Extract name
        name_element = await element.query_selector('.panel-heading .fake-link')
        name = await name_element.text_content() if name_element else ""
        name = name.strip() if name else ""
        
        # Extract date and time information
        date_elements = await element.query_selector_all('.panel-body .when')
        
        date = ""
        start_time = ""
        end_time = ""
        
        if date_elements and len(date_elements) > 0:
            date_text = await date_elements[0].text_content()
            date_parts = date_text.split(',')
            
            if len(date_parts) > 1:
                date = date_parts[1].strip()
            
            if len(date_parts) > 2:
                start_time = date_parts[2].strip()
        
        if date_elements and len(date_elements) > 1:
            end_time_text = await date_elements[1].text_content()
            end_time = end_time_text.strip()
        
        # Extract price
        price = ""
        price_elements = await element.query_selector_all(".panel-body .ng-binding")
        
        for price_el in price_elements:
            price_text = await price_el.text_content()
            if "$" in price_text:
                price = price_text.replace("$", "").strip()
        
        # Check if the facility can be reserved
        reserve_button = await element.query_selector('button[ng-click*="vm.onReserve"]')
        can_reserve = False
        button_id = None
        
        if reserve_button:
            # Check if button has 'disabled' class
            button_classes = await reserve_button.get_attribute('class')
            can_reserve = 'disabled' not in button_classes if button_classes else False
            
            # Get button ID if available
            button_id = await reserve_button.get_attribute('id')
        
        # Add the extracted data to the result array
        reservations.append({
            'name': name,
            'date': date,
            'startTime': generate_time_object(date, start_time) if start_time else None,
            'endTime': generate_time_object(date, end_time) if end_time else None,
            'price': price,
            'canReserve': can_reserve,
            'buttonId': button_id
        })

    return reservations

async def check_available_courts(args):
    """Check available badminton courts and return results."""
    is_headless = args.headless
    slow_mo_value = args.slow
    test_mode = args.test

    # Get neighborhoods from environment variables
    neighborhoods_str = os.environ.get('NEIGHBORHOODS', '')
    neighborhoods = [n.strip() for n in neighborhoods_str.split(',')]
    
    select_time = True
    TIME_TO_WAIT_FOR_SEARCH_RESULTS = 12000  # 12 seconds
    
    async with async_playwright() as p:
        # Browser Launch options
        browser = await p.chromium.launch(
            headless=is_headless,
            slow_mo=slow_mo_value
        )

        context = await browser.new_context(
            locale='en-US',
            timezone_id='America/New_York',  # This sets the browser timezone to Eastern Time
        )
        
        page = await context.new_page()
        
        # Get the booking URL from the .env file
        url = os.getenv('BOOKING_URL', '')
        if not url:
            print("Please set the BOOKING_URL environment variable.")
            return None
        
        await page.goto(url)

        # Accept cookies
        await page.get_by_role("button", name="Accepter tout").click()

        # Click on 'Reserve a space' link
        await page.get_by_role("link", name="Réservation d'un terrain").click()
        
        # Click on Badminton
        await page.get_by_role("link", name="Badminton Badminton Consultez").click()

        # Select Neighborhood based on environment variable
        await page.get_by_text('Arrondissement Tous').click()
        
        # Check each neighborhood in the list
        for neighborhood in neighborhoods:
            try:
                print(f"Selecting neighborhood: {neighborhood}")
                await page.get_by_role('checkbox', name=neighborhood).check()
            except Exception as e:
                print(f"Could not find neighborhood: {neighborhood}. Error: {e}")
                
        await page.get_by_role('button', name='Confirmer').click()
        
        if select_time:
            await select_time_on_page(page)
            
        # Select the date from the calendar for the next 4 days, clicking all matching buttons for each date
        calendar_button = page.locator('#u6510_btnFacilityReservationSearchReserveDateCalendar').nth(0)
        for date in generate_selected_date():
            await calendar_button.click()  # Open the calendar
            date_buttons = await page.locator(f'button:has(span:has-text("{date}"))').all()
            for i, button in enumerate(date_buttons):
                await button.click()
                if i < len(date_buttons) - 1:  # Reopen the calendar if not the last button
                    await calendar_button.click()
        
        # Wait for search results to load
        try:
            # Wait for reservation panels to appear
            await page.wait_for_selector('.panel.panel-default.panel-facilityReservation', timeout=TIME_TO_WAIT_FOR_SEARCH_RESULTS)
        except Exception as e:
            print('Finished waiting for the calendar.')
        
        # Extract reservation data
        reservation_elements = await page.query_selector_all('.panel.panel-default.panel-facilityReservation')
        reservations = await generate_available_booking_list(reservation_elements)
        
        # Capture current URL before closing the browser
        current_url = page.url
        
        # Prepare results data
        result_data = {
            'reservations': reservations,
            'url': current_url,
            'timestamp': datetime.now().isoformat(),
            'timezone': datetime.now().astimezone().tzname()
        }
        
        if test_mode:
            with open('docs/badminton_results.json', 'w') as f:
                json.dump(result_data, f, indent=2, default=str)
            print('Results saved to data/badminton_results.json')
        
        await browser.close()
        return result_data