import { CommonModule } from '@angular/common';
import {Component } from'@angular/core';
import { FormControl } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatDividerModule } from '@angular/material/divider';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';

@Component({
    selector: 'login-page',
    standalone: true,
    imports: [
        MatCardModule,
        MatDividerModule,
        MatFormFieldModule,
        MatInputModule,
        CommonModule,
    ],
    templateUrl: './login.component.html',
    styleUrls: ['./login.component.scss'],
})

export class LoginComponent {
    usernameFormControl = new FormControl('');
}