import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, signal } from '@angular/core'
import { MatGridListModule } from '@angular/material/grid-list';


@Component({
    selector: 'main-content',
    standalone: true,
    imports: [
        CommonModule,
        MatGridListModule,
    ],
    templateUrl: './main-content.component.html',
    styleUrls: ['./main-content.component.scss'],
    changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MainContentComponent {
    portfolioValue = signal(5234.20)
    portfolioPercentage = computed(() => {
        const target = 10000;
        return Math.floor((this.portfolioValue() / target) * 100);
    });
    portfolioProgress = computed(() => {
        const circumference = 251.2;
        return circumference - (circumference * this.portfolioPercentage()) / 100;
    });
}